from datetime import datetime, date

from fastapi import APIRouter
from tortoise.expressions import Q
from pydantic import BaseModel, Field, field_validator
from model import IncomeOrder, SalesOrder
from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist
from typing import Optional
import pandas as pd
import io
from fastapi import UploadFile, File, Depends
from auth import get_current_user  # 导入权限相关依赖

def require_roles_dep(allowed_roles: list):
    async def dependency(current_user: dict = Depends(get_current_user)):
        if current_user["user_type"] == "admin" or current_user["user_type"] in allowed_roles:
            return current_user
        raise HTTPException(status_code=403, detail="权限不足")
    return dependency

# 定义依赖对象
income_only = require_roles_dep(['incomer', 'invoicer']) # invoicer

# 创建自己这个模块的Router路由对象
router = APIRouter(dependencies=[Depends(income_only)])

@router.get("/")
def index():
    return "hello incomes index"

@router.get("/incomes/")
async def get_income_orders():  # 修改函数名，避免混淆
    income_orders = await IncomeOrder.all()
    return income_orders

@router.get("/sales/filter/")
async def filter_income_orders(
    sales_order_id: Optional[str] = None,  # 修改参数名，保持一致
    bankorbill: Optional[str] = None,
    amount: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    description: Optional[str] = None
):
    filters = []
    if sales_order_id:  # 修改字段名
        filters.append(Q(sales_order_id=sales_order_id))
    if bankorbill:
        filters.append(Q(bankorbill=bankorbill))
    if amount is not None:
        filters.append(Q(amount=amount))
    if start_date is not None:
        filters.append(Q(created_at__gte=datetime.combine(start_date, datetime.min.time())))
    if end_date is not None:
        filters.append(Q(created_at__lte=datetime.combine(end_date, datetime.max.time())))
    if description:
        filters.append(Q(description__contains=description))

    if filters:
        query = filters.pop()
        for f in filters:
            query &= f
        income_orders = await IncomeOrder.filter(query)
    else:
        income_orders = await IncomeOrder.all()
    return income_orders

# 定义Pydantic模型用于数据验证
class IncomeOrderCreate(BaseModel):
    sales_order_id: str  # 修改为str类型，与SalesOrder的主键类型一致
    bankorbill: str
    amount: float = Field(gt=0, description="金额必须大于0")
    description: Optional[str] = None

@router.post("/incomes/")
async def create_income_order(income_order: IncomeOrderCreate):
    try:
        # 验证 sales_order 是否存在
        sales_order = await SalesOrder.get_or_none(id=income_order.sales_order_id)
        if not sales_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"销售订单 {income_order.sales_order_id} 不存在"
            )
        
        # 创建一个新的收入订单实例
        new_income_order = await IncomeOrder.create(
            sales_order_id=income_order.sales_order_id,
            bankorbill=income_order.bankorbill,
            amount=income_order.amount,
            description=income_order.description,
            created_at=datetime.now()
        )
        return new_income_order
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建收入订单失败: {str(e)}"
        )

@router.post("/incomes/import/")
async def import_income_orders(file: UploadFile = File(...)):
    # 验证文件类型
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx files are supported"
        )

    try:
        # 读取 Excel 文件
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))

        # 验证必要列是否存在
        required_columns = {'sales_order_id', 'bankorbill', 'amount'}
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Excel file must contain columns: {', '.join(required_columns)}"
            )

        # 存储导入的收入订单
        created_orders = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # 验证数据
                if pd.isna(row['amount']) or row['amount'] <= 0:
                    errors.append(f"行 {index + 2}: 金额无效")
                    continue
                
                if pd.isna(row['sales_order_id']):
                    errors.append(f"行 {index + 2}: sales_order_id 不能为空")
                    continue

                # 验证 sales_order 是否存在
                sales_order_id = str(row['sales_order_id'])
                sales_order = await SalesOrder.get_or_none(id=sales_order_id)
                if not sales_order:
                    errors.append(f"行 {index + 2}: 销售订单 {sales_order_id} 不存在")
                    continue

                # 创建收入订单
                income_order = await IncomeOrder.create(
                    sales_order_id=sales_order_id,
                    bankorbill=str(row['bankorbill']),
                    amount=float(row['amount']),  # 修改为float
                    description=str(row['description']) if 'description' in row and pd.notna(row['description']) else None,
                    created_at=datetime.now()
                )
                created_orders.append(income_order)
                
            except Exception as e:
                errors.append(f"行 {index + 2}: {str(e)}")
                continue

        if not created_orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"没有成功导入任何收入订单。错误信息: {'; '.join(errors)}"
            )

        result = {
            "message": f"成功导入 {len(created_orders)} 个收入订单",
            "imported_count": len(created_orders),
            "imported_orders": created_orders
        }
        
        if errors:
            result["warnings"] = errors
            
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理文件时出错: {str(e)}"
        )

class IncomeOrderUpdate(BaseModel):
    sales_order_id: Optional[str] = None  # 修改字段名和类型
    bankorbill: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0, description="金额必须大于0")  # 修改为float
    description: Optional[str] = None

@router.put("/incomes/{income_order_id}")
async def update_income_order(income_order_id: int, income_order: IncomeOrderUpdate):
    try:
        db_order = await IncomeOrder.get_or_none(id=income_order_id)
        if not db_order:
            raise HTTPException(status_code=404, detail="这个IncomeOrder不存在")

        update_data = income_order.dict(exclude_unset=True)
        
        # 如果要更新 sales_order_id，验证其存在性
        if 'sales_order_id' in update_data:
            sales_order = await SalesOrder.get_or_none(id=update_data['sales_order_id'])
            if not sales_order:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"销售订单 {update_data['sales_order_id']} 不存在"
                )
        
        for key, value in update_data.items():
            setattr(db_order, key, value)
        await db_order.save()
        return db_order
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新收入订单失败: {str(e)}"
        )

@router.delete("/incomes/{income_order_id}")
async def delete_income_order(income_order_id: int):
    try:
        income_order = await IncomeOrder.get_or_none(id=income_order_id)
        if not income_order:
            raise HTTPException(status_code=404, detail="这个IncomeOrder不存在")

        await income_order.delete()
        return {"message": "IncomeOrder删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除收入订单失败: {str(e)}"
        )
