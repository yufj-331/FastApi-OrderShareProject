from datetime import datetime

from fastapi import APIRouter
from tortoise.expressions import Q
from pydantic import BaseModel, Field
from pydantic import BaseModel, field_validator
from model import SalesOrder
from fastapi import HTTPException, status, Depends
from tortoise.exceptions import DoesNotExist
from typing import Optional
import pandas as pd
import io
from fastapi import UploadFile, File
from auth import  get_current_user  # 导入权限相关依赖

def require_roles_dep(allowed_roles: list):
    async def dependency(current_user: dict = Depends(get_current_user)):
        if current_user["user_type"] == "admin" or current_user["user_type"] in allowed_roles:
            return current_user
        raise HTTPException(status_code=403, detail="权限不足")
    return dependency

# 定义依赖对象
saler_only = require_roles_dep(['saler'])

# 创建自己这个模块的Router路由对象，设置访问权限用户为saler
router = APIRouter()

saler_incomer_ivoicer = require_roles_dep(['saler', 'incomer', 'ivoicer'])

@router.get("/", dependencies=[Depends(saler_only)])
def index():
    return "hello sales index"

@router.get("/sales/", dependencies=[Depends(saler_incomer_ivoicer)])
async def get_sales_orders():
    sales_orders = await SalesOrder.all()
    return sales_orders


@router.get("/sales/filter/", dependencies=[Depends(saler_incomer_ivoicer)])
async def filter_sales_orders(
    product_name: Optional[str] = None,
    product_name_like: bool = False,
    customer_name: Optional[str] = None,
    customer_name_like: bool = False,
    quantity_min: Optional[int] = None,
    quantity_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
):
    filters = []
    if product_name:
        if product_name_like:
            filters.append(Q(product_name__contains=product_name))
        else:
            filters.append(Q(product_name=product_name))
    if customer_name:
        if customer_name_like:
            filters.append(Q(customer_name__contains=customer_name))
        else:
            filters.append(Q(customer_name=customer_name))
    if quantity_min is not None:
        filters.append(Q(quantity__gte=quantity_min))
    if quantity_max is not None:
        filters.append(Q(quantity__lte=quantity_max))
    if price_min is not None:
        filters.append(Q(price_per_unit__gte=price_min))
    if price_max is not None:
        filters.append(Q(price_per_unit__lte=price_max))

    if filters:
        query = filters.pop()
        for f in filters:
            query &= f
        sales_orders = await SalesOrder.filter(query)
    else:
        sales_orders = await SalesOrder.all()
    return sales_orders

# 定义Pydantic模型用于数据验证
class salesorderCreate(BaseModel):
    customer_name: str 
    product_name: str 
    quantity: int = Field(gt=0, description="数量必须大于0") 
    price_per_unit: float = Field(gt=0, description="单价必须大于等于0")

@router.post("/sales/", dependencies=[Depends(saler_only)])
async def create_sales_order(sales_order: salesorderCreate):
    # 创建一个新的销售订单实例
    new_sales_order = await SalesOrder.create(
        customer_name=sales_order.customer_name,
        product_name=sales_order.product_name,
        quantity=sales_order.quantity,
        price_per_unit=sales_order.price_per_unit,
        created_at=datetime.now()
    )
    return new_sales_order

@router.post("/sales/import/", dependencies=[Depends(saler_only)])
async def import_sales_orders(file: UploadFile = File(...)):
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
        required_columns = {'customer_name', 'product_name', 'quantity', 'price_per_unit'}
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Excel file must contain columns: {', '.join(required_columns)}"
            )

        # 存储导入的销售订单
        created_orders = []
        for _, row in df.iterrows():
            try:
                # 验证数据
                if row['quantity'] <= 0 or row['price_per_unit'] <= 0:
                    continue  # 跳过无效数据行

                # 创建销售订单
                sales_order = await SalesOrder.create(
                    customer_name=str(row['customer_name']),
                    product_name=str(row['product_name']),
                    quantity=int(row['quantity']),
                    price_per_unit=float(row['price_per_unit']),
                    created_at=datetime.now()
                )
                created_orders.append(sales_order)
            except (ValueError, TypeError):
                continue  # 跳过有错误的数据行

        if not created_orders:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid sales orders were imported"
            )

        return {
            "message": f"Successfully imported {len(created_orders)} sales orders",
            "imported_orders": created_orders
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )

class salesorderUpdate(BaseModel):
    customer_name: str 
    product_name: str 
    quantity: int = Field(gt=0, description="数量必须大于0") 
    price_per_unit: float = Field(gt=0, description="单价必须大于等于0")

@router.put("/sales/{sales_order_id}", dependencies=[Depends(saler_only)])
async def update_sales_order(sales_order_id: int, sales_order: salesorderUpdate):
    db_order = await SalesOrder.get_or_none(id=sales_order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="这个SalesOrder不存在")

    update_data = sales_order.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_order, key, value)
    await db_order.save()
    return db_order

@router.delete("/sales/{sales_order_id}", dependencies=[Depends(saler_only)])
async def delete_sales_order(sales_order_id: int):
    sales_order = await SalesOrder.get_or_none(id=sales_order_id)
    if not sales_order:
        raise HTTPException(status_code=404, detail="这个SalesOrder不存在")

    await sales_order.delete()
    return {"message": "SalesOrder删除成功"}