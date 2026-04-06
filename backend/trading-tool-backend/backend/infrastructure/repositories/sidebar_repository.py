from sqlalchemy.ext.asyncio import AsyncSession

class SidebarRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
