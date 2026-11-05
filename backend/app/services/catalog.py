import json
from pathlib import Path
from typing import Protocol
from sqlalchemy import select
from app.models.entities import Product

class ProductProvider(Protocol):
    def discover(self, categories: list[str] | None = None) -> list[dict]: ...

class LocalCatalogProvider:
    def __init__(self, db):
        self.db = db

    def discover(self, categories: list[str] | None = None):
        return [p.data for p in self.db.scalars(select(Product)) if categories is None or p.data["category"] in categories]

def seed(db):
    products = json.loads((Path(__file__).parents[2] / "data/laptops.json").read_text())
    products += json.loads((Path(__file__).parents[2] / "data/accessories.json").read_text())
    for product in products:
        if not db.get(Product, product["id"]):
            db.add(Product(id=product["id"], data=product))
    db.commit()

if __name__ == "__main__":
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        seed(db)
