from datetime import datetime, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import pandas as pd
from io import StringIO
from model import SalesOrder, IncomeOrder, InvoiceOrder
from auth import get_current_user
from fastapi.responses import StreamingResponse
import io

def require_roles_dep(allowed_roles: list):
    async def dependency(current_user: dict = Depends(get_current_user)):
        if current_user["user_type"] == "admin" or current_user["user_type"] in allowed_roles:
            return current_user
        raise HTTPException(status_code=403, detail="权限不足")
    return dependency

# 定义依赖对象
report_only = require_roles_dep(['incomer', 'invoicer']) # invoicer

# 创建路由对象
router = APIRouter(dependencies=[Depends(report_only)])
# ['id', 'customer_name', 'product_name', 'quantity', 'price_per_unit',
#       'total_amount', 'created_at_x', 'created_at_y', 'amount_x',
#      'invoice_number', 'amount_y', 'tax_amount']
class ReportFilter(BaseModel):
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    date_start: Optional[date] = None   # 开始日期
    date_end: Optional[date] = None     # 结束日期
    min_total_amount: Optional[float] = None  # 最小总金额
    max_total_amount: Optional[float] = None  # 最大总金额

@router.post("/overview/")
async def get_report_overview(filter: ReportFilter) -> Dict[str, Any]:
    # 查询数据
    sales_orders = await SalesOrder.all().values()
    income_orders = await IncomeOrder.all().values()
    invoice_orders = await InvoiceOrder.all().values()

    # 转为DataFrame
    df_sales = pd.DataFrame(sales_orders)
    df_income = pd.DataFrame(income_orders)
    df_invoice = pd.DataFrame(invoice_orders)

    # 类型转换和预处理
    if not df_sales.empty:
        df_sales['created_at'] = pd.to_datetime(df_sales['created_at']).dt.date

        # 过滤功能
        if filter.customer_name:
            df_sales = df_sales[df_sales['customer_name'] == filter.customer_name]
        if filter.product_name:
            df_sales = df_sales[df_sales['product_name'] == filter.product_name]
        if filter.date_start:
            df_sales = df_sales[df_sales['created_at'] >= filter.date_start]
        if filter.date_end:
            df_sales = df_sales[df_sales['created_at'] <= filter.date_end]
        if filter.min_total_amount is not None:
            df_sales = df_sales[df_sales['total_amount'] >= filter.min_total_amount]
        if filter.max_total_amount is not None:
            df_sales = df_sales[df_sales['total_amount'] <= filter.max_total_amount]

    # 类型转换和预处理
    if not df_sales.empty:
        df_sales['created_at'] = pd.to_datetime(df_sales['created_at']).dt.date

    if not df_income.empty:
        df_income_type = {
            'amount': 'float64',
            'created_at': 'datetime64[ns]',
        }
        df_income = df_income.astype(df_income_type, copy=False, errors='ignore')
        df_income['created_at'] = pd.to_datetime(df_income['created_at'], errors='coerce').dt.date
        df_income.drop(columns=['id'], inplace=True, errors='ignore')

    if not df_invoice.empty:
        df_invoice_type = {
            'amount': 'float64',
            'tax_amount': 'float64',
            'created_at': 'datetime64[ns]',
        }
        df_invoice = df_invoice.astype(df_invoice_type, copy=False, errors='ignore')
        df_invoice['created_at'] = pd.to_datetime(df_invoice['created_at'], errors='coerce').dt.date
        df_invoice.drop(columns=['id'], inplace=True, errors='ignore')

    # 合并数据
    df_conbination_1 = pd.merge(
        df_sales, df_income, left_on='id', right_on='sales_order_id', how='left'
    )
    df_conbination_2 = pd.merge(
        df_conbination_1, df_invoice, left_on='id', right_on='sales_order_id', how='left'
    )

    # 分组聚合
    df_bulk = df_conbination_2.groupby(
        ['id', 'customer_name', 'product_name', 'quantity', 'price_per_unit', 'total_amount', 'created_at_x'],
        dropna=False
    ).agg({
        'created_at_y': lambda x: '\n'.join(x.dropna().astype(str)),
        'amount_x': 'sum',
        'invoice_number': lambda x: '\n'.join(x.dropna().astype(str)),
        'amount_y': 'sum',
        'tax_amount': 'sum'
    }).reset_index()

    # 返回为json
    return {"data": df_bulk.fillna('').to_dict(orient='records')}

@router.post("/overview/download/")
async def download_report_excel(filter: ReportFilter):
    # 查询数据
    sales_orders = await SalesOrder.all().values()
    income_orders = await IncomeOrder.all().values()
    invoice_orders = await InvoiceOrder.all().values()

    # 转为DataFrame
    df_sales = pd.DataFrame(sales_orders)
    df_income = pd.DataFrame(income_orders)
    df_invoice = pd.DataFrame(invoice_orders)

    # 类型转换和预处理（同 overview 逻辑）
    if not df_sales.empty:
        df_sales['created_at'] = pd.to_datetime(df_sales['created_at']).dt.date
        if filter.customer_name:
            df_sales = df_sales[df_sales['customer_name'] == filter.customer_name]
        if filter.product_name:
            df_sales = df_sales[df_sales['product_name'] == filter.product_name]
        if filter.date_start:
            df_sales = df_sales[df_sales['created_at'] >= filter.date_start]
        if filter.date_end:
            df_sales = df_sales[df_sales['created_at'] <= filter.date_end]
        if filter.min_total_amount is not None:
            df_sales = df_sales[df_sales['total_amount'] >= filter.min_total_amount]
        if filter.max_total_amount is not None:
            df_sales = df_sales[df_sales['total_amount'] <= filter.max_total_amount]

    if not df_income.empty:
        df_income_type = {
            'amount': 'float64',
            'created_at': 'datetime64[ns]',
        }
        df_income = df_income.astype(df_income_type, copy=False, errors='ignore')
        df_income['created_at'] = pd.to_datetime(df_income['created_at'], errors='coerce').dt.date
        df_income.drop(columns=['id'], inplace=True, errors='ignore')

    if not df_invoice.empty:
        df_invoice_type = {
            'amount': 'float64',
            'tax_amount': 'float64',
            'created_at': 'datetime64[ns]',
        }
        df_invoice = df_invoice.astype(df_invoice_type, copy=False, errors='ignore')
        df_invoice['created_at'] = pd.to_datetime(df_invoice['created_at'], errors='coerce').dt.date
        df_invoice.drop(columns=['id'], inplace=True, errors='ignore')

    # 合并数据
    df_conbination_1 = pd.merge(
        df_sales, df_income, left_on='id', right_on='sales_order_id', how='left'
    )
    df_conbination_2 = pd.merge(
        df_conbination_1, df_invoice, left_on='id', right_on='sales_order_id', how='left'
    )

    # 分组聚合
    df_bulk = df_conbination_2.groupby(
        ['id', 'customer_name', 'product_name', 'quantity', 'price_per_unit', 'total_amount', 'created_at_x'],
        dropna=False
    ).agg({
        'created_at_y': lambda x: '\n'.join(x.dropna().astype(str)),
        'amount_x': 'sum',
        'invoice_number': lambda x: '\n'.join(x.dropna().astype(str)),
        'amount_y': 'sum',
        'tax_amount': 'sum'
    }).reset_index()

    # 写入Excel到内存
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_bulk.fillna('').to_excel(writer, index=False, sheet_name='Report')
    output.seek(0)

    # 返回文件流
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=report_overview.xlsx"}
    )

