from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from uvicorn import run
from tortoise.contrib.fastapi import register_tortoise
from tortoise.transactions import in_transaction
from tortoise.exceptions import DBConnectionError

from income_order import router as IncomeOrder
from InvoiceOrder import router as InvoiceOrder
from SalesOrder import router as SalesOrder
from auth import router as auth_router

from report import router as report_router
from fastapi.templating import Jinja2Templates

app = FastAPI()

 # HTML模板文件目录，自己新建templates目录
templates = Jinja2Templates(directory="templates")

# 注册其他的模块的route，指定URL前缀，以及docs可以使用的tags
app.include_router(IncomeOrder, prefix="/income", tags=["income"])
app.include_router(InvoiceOrder, prefix="/invoice", tags=["invoice"])
app.include_router(SalesOrder, prefix="/sales", tags=["sales"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(report_router, prefix="/report", tags=["report"])


@app.get("/", tags=["home"])
def read_root():
    return {"Hello": "World"}

@app.get("/db_test", tags=["test"])
async def db_test():
    try:
        async with in_transaction() as conn:
            await conn.execute_query("SELECT 1")
        return {"status": "success", "msg": "数据库连接成功"}
    except DBConnectionError as e:
        return {"status": "fail", "msg": f"数据库连接失败: {str(e)}"}
    except Exception as e:
        return {"status": "fail", "msg": f"其他错误: {str(e)}"}

# 注册 Tortoise ORM
register_tortoise(
    app,
    db_url="mysql://root:920331@localhost:3306/orderregistrationform",
    modules={"models": ["model"]},
    generate_schemas=False,  # 自动生成数据库表结构
    add_exception_handlers=True,  # 添加Tortoise ORM的异常处理程序
)

if __name__ == "__main__":
    run(app, port=8000)
