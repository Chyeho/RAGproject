'''
文档管理路由
'''
from fastapi import APIRouter

router = APIRouter(prefix="/api/documents",tags=["documents"])

@router.get("categories")
async def get_categories():
    pass