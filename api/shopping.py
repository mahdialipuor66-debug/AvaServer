from fastapi import APIRouter

router = APIRouter()

@router.get("/shopping")
def shopping():

    return [
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