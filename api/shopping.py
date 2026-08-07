from fastapi import APIRouter, Query

router = APIRouter()

products = [
    {
        "title": "برنج ایرانی",
        "price": 850000
    },
    {
        "title": "تلویزیون سامسونگ",
        "price": 15000000
    },
    {
        "title": "روغن خوراکی",
        "price": 75000
    }
]


@router.get("/shopping")
def shopping(q: str = Query(default="")):

    if q == "":
        return products

    result = []

    q = q.strip().lower()

    for product in products:

        if q in product["title"].lower():

            result.append(product)

    return result