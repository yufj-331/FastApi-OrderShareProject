from tortoise import fields
from tortoise.models import Model

class SalesOrder(Model):
    id = fields.CharField(pk=True, max_length=16, null=False, unique=True)
    customer_name = fields.CharField(max_length=255)
    product_name = fields.CharField(max_length=255)
    quantity = fields.IntField()
    price_per_unit = fields.DecimalField(max_digits=10, decimal_places=2)
    total_amount = fields.DecimalField(max_digits=10, decimal_places=2)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    async def save(self, *args, **kwargs):
        # 在保存前自动计算 total_amount
        self.total_amount = self.quantity * self.price_per_unit
        await super().save(*args, **kwargs)
    
    class Meta:
        table = "sales_orders"

class IncomeOrder(Model):
    id = fields.IntField(pk=True)
    sales_order = fields.ForeignKeyField('models.SalesOrder', related_name='incomes')
    bankorbill = fields.CharField(max_length=255)
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    created_at = fields.DatetimeField(auto_now_add=True)
    description = fields.CharField(max_length=255, null=True)

    class Meta:
        table = "income_orders"

class InvoiceOrder(Model):
    id = fields.IntField(pk=True)
    # related_name='goods' 参数用于指定反向关系的名称
    # 假设你有一个 Warehouse 实例，通过warehouse_instance.goods.all()可以访问关联的Goods
    sales_order = fields.ForeignKeyField('models.SalesOrder', related_name='invoices')
    invoice_number = fields.CharField(max_length=255)
    invoice_date = fields.DatetimeField()
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    # 税额
    tax_amount = fields.DecimalField(max_digits=10, decimal_places=2, null=True)
    invoice_type = fields.CharField(max_length=255) # 发票类型，要么是普通发票，要么是增值税发票
    # 开票日期
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "invoice_orders"

class User(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True, description="用户名")
    hashed_password = fields.CharField(max_length=128, description="加密后的密码")
    USER_TYPE_CHOICES = [
    ("saler", "销售管理员"),
    ("incomer", "收入管理员"),
    ("ivoicer", "发票管理员"),
    ("admin", "超级管理员"),
] # 有了ORM限制，数据库中无需再做约束
    user_type = fields.CharField(max_length=10, choices=USER_TYPE_CHOICES, description="用户类型：saler=销售管理员，incomer=收入管理员，ivoicer=发票管理员，admin=超级管理员")
    is_active = fields.BooleanField(default=True, description="用户是否活跃")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")
    
    def __str__(self):
        return self.username

