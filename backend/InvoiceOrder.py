from datetime import datetime, date

from fastapi import APIRouter
from tortoise.expressions import Q
from pydantic import BaseModel, Field, field_validator
from model import InvoiceOrder, SalesOrder
from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist
from typing import Optional, Literal
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
invoice_only = require_roles_dep(['incomer', 'invoicer'])
# 创建自己这个模块的Router路由对象
router = APIRouter(dependencies=[Depends(invoice_only)])

@router.get("/")
def index():
    return "hello invoices index"

@router.get("/invoices/")
async def get_invoice_orders():
    invoice_orders = await InvoiceOrder.all()
    return invoice_orders

@router.get("/invoices/filter/")
async def filter_invoice_orders(
    sales_order_id: Optional[str] = None,
    invoice_number: Optional[str] = None,
    invoice_type: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    invoice_date_start: Optional[date] = None,
    invoice_date_end: Optional[date] = None
):
    filters = []
    if sales_order_id:
        filters.append(Q(sales_order_id=sales_order_id))
    if invoice_number:
        filters.append(Q(invoice_number__contains=invoice_number))
    if invoice_type:
        filters.append(Q(invoice_type=invoice_type))
    if amount_min is not None:
        filters.append(Q(amount__gte=amount_min))
    if amount_max is not None:
        filters.append(Q(amount__lte=amount_max))
    if start_date is not None:
        filters.append(Q(created_at__gte=datetime.combine(start_date, datetime.min.time())))
    if end_date is not None:
        filters.append(Q(created_at__lte=datetime.combine(end_date, datetime.max.time())))
    if invoice_date_start is not None:
        filters.append(Q(invoice_date__gte=datetime.combine(invoice_date_start, datetime.min.time())))
    if invoice_date_end is not None:
        filters.append(Q(invoice_date__lte=datetime.combine(invoice_date_end, datetime.max.time())))

    if filters:
        query = filters.pop()
        for f in filters:
            query &= f
        invoice_orders = await InvoiceOrder.filter(query)
    else:
        invoice_orders = await InvoiceOrder.all()
    return invoice_orders

# 定义Pydantic模型用于数据验证
class InvoiceOrderCreate(BaseModel):
    sales_order_id: str  # 外键，关联sales_order
    invoice_number: str = Field(..., min_length=1, description="发票号码不能为空")
    invoice_date: datetime = Field(..., description="发票日期")
    amount: float = Field(gt=0, description="金额必须大于0")
    tax_amount: Optional[float] = Field(default=None, ge=0, description="税额必须大于等于0")
    invoice_type: Literal["普通发票", "增值税发票"] = Field(..., description="发票类型")

    @field_validator('invoice_date')
    @classmethod
    def validate_invoice_date(cls, v):
        if v > datetime.now():
            raise ValueError('发票日期不能是未来时间')
        return v

@router.post("/invoices/")
async def create_invoice_order(invoice_order: InvoiceOrderCreate):
    try:
        # 验证 sales_order 是否存在
        sales_order = await SalesOrder.get_or_none(id=invoice_order.sales_order_id)
        if not sales_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"销售订单 {invoice_order.sales_order_id} 不存在"
            )
        
        # 检查发票号码是否已存在
        existing_invoice = await InvoiceOrder.get_or_none(invoice_number=invoice_order.invoice_number)
        if existing_invoice:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"发票号码 {invoice_order.invoice_number} 已存在"
            )
        
        # 创建一个新的发票订单实例
        new_invoice_order = await InvoiceOrder.create(
            sales_order_id=invoice_order.sales_order_id,
            invoice_number=invoice_order.invoice_number,
            invoice_date=invoice_order.invoice_date,
            amount=invoice_order.amount,
            tax_amount=invoice_order.tax_amount,
            invoice_type=invoice_order.invoice_type,
            created_at=datetime.now()
        )
        return new_invoice_order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建发票订单失败: {str(e)}"
        )

@router.post("/invoices/import/")
async def import_invoice_orders(file: UploadFile = File(...)):
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
        required_columns = {'sales_order_id', 'invoice_number', 'invoice_date', 'amount', 'invoice_type'}
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Excel file must contain columns: {', '.join(required_columns)}"
            )

        # 存储导入的发票订单
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
                
                if pd.isna(row['invoice_number']):
                    errors.append(f"行 {index + 2}: invoice_number 不能为空")
                    continue
                
                if pd.isna(row['invoice_date']):
                    errors.append(f"行 {index + 2}: invoice_date 不能为空")
                    continue
                
                if pd.isna(row['invoice_type']) or row['invoice_type'] not in ['普通发票', '增值税发票']:
                    errors.append(f"行 {index + 2}: invoice_type 必须是'普通发票'或'增值税发票'")
                    continue

                # 验证 sales_order 是否存在
                sales_order_id = str(row['sales_order_id'])
                sales_order = await SalesOrder.get_or_none(id=sales_order_id)
                if not sales_order:
                    errors.append(f"行 {index + 2}: 销售订单 {sales_order_id} 不存在")
                    continue

                # 检查发票号码是否已存在
                invoice_number = str(row['invoice_number'])
                existing_invoice = await InvoiceOrder.get_or_none(invoice_number=invoice_number)
                if existing_invoice:
                    errors.append(f"行 {index + 2}: 发票号码 {invoice_number} 已存在")
                    continue

                # 处理日期
                invoice_date = pd.to_datetime(row['invoice_date'])
                if invoice_date > datetime.now():
                    errors.append(f"行 {index + 2}: 发票日期不能是未来时间")
                    continue

                # 处理税额
                tax_amount = None
                if 'tax_amount' in row and pd.notna(row['tax_amount']):
                    tax_amount = float(row['tax_amount'])
                    if tax_amount < 0:
                        errors.append(f"行 {index + 2}: 税额不能为负数")
                        continue

                # 创建发票订单
                invoice_order = await InvoiceOrder.create(
                    sales_order_id=sales_order_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    amount=float(row['amount']),
                    tax_amount=tax_amount,
                    invoice_type=str(row['invoice_type']),
                    created_at=datetime.now()
                )
                created_orders.append(invoice_order)
                
            except Exception as e:
                errors.append(f"行 {index + 2}: {str(e)}")
                continue

        if not created_orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"没有成功导入任何发票订单。错误信息: {'; '.join(errors)}"
            )

        result = {
            "message": f"成功导入 {len(created_orders)} 个发票订单",
            "imported_count": len(created_orders),
            "imported_orders": created_orders
        }
        
        if errors:
            result["warnings"] = errors
            
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理文件时出错: {str(e)}"
        )

class InvoiceOrderUpdate(BaseModel):
    sales_order_id: Optional[str] = None
    invoice_number: Optional[str] = Field(default=None, min_length=1, description="发票号码不能为空")
    invoice_date: Optional[datetime] = None
    amount: Optional[float] = Field(default=None, gt=0, description="金额必须大于0")
    tax_amount: Optional[float] = Field(default=None, ge=0, description="税额必须大于等于0")
    invoice_type: Optional[Literal["普通发票", "增值税发票"]] = None

    @field_validator('invoice_date')
    @classmethod
    def validate_invoice_date(cls, v):
        if v is not None and v > datetime.now():
            raise ValueError('发票日期不能是未来时间')
        return v

@router.put("/invoices/{invoice_order_id}")
async def update_invoice_order(invoice_order_id: int, invoice_order: InvoiceOrderUpdate):
    try:
        db_order = await InvoiceOrder.get_or_none(id=invoice_order_id)
        if not db_order:
            raise HTTPException(status_code=404, detail="这个InvoiceOrder不存在")

        update_data = invoice_order.dict(exclude_unset=True)
        
        # 如果要更新 sales_order_id，验证其存在性
        if 'sales_order_id' in update_data:
            sales_order = await SalesOrder.get_or_none(id=update_data['sales_order_id'])
            if not sales_order:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"销售订单 {update_data['sales_order_id']} 不存在"
                )
        
        # 如果要更新发票号码，检查是否重复
        if 'invoice_number' in update_data:
            existing_invoice = await InvoiceOrder.filter(
                invoice_number=update_data['invoice_number']
            ).exclude(id=invoice_order_id).first()
            if existing_invoice:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"发票号码 {update_data['invoice_number']} 已存在"
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
            detail=f"更新发票订单失败: {str(e)}"
        )

@router.delete("/invoices/{invoice_order_id}")
async def delete_invoice_order(invoice_order_id: int):
    try:
        invoice_order = await InvoiceOrder.get_or_none(id=invoice_order_id)
        if not invoice_order:
            raise HTTPException(status_code=404, detail="这个InvoiceOrder不存在")

        await invoice_order.delete()
        return {"message": "InvoiceOrder删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除发票订单失败: {str(e)}"
        )

@router.get("/invoices/{invoice_order_id}")
async def get_invoice_order_by_id(invoice_order_id: int):
    try:
        invoice_order = await InvoiceOrder.get_or_none(id=invoice_order_id)
        if not invoice_order:
            raise HTTPException(status_code=404, detail="这个InvoiceOrder不存在")
        return invoice_order
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取发票订单失败: {str(e)}"
        )
