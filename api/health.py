from fastapi import APIRouter, Query, HTTPException
import re
import requests
from urllib.parse import quote

router = APIRouter(
    prefix="/health",
    tags=["Health"]
)

PAZIRESH24_SEARCH_URL = "https://apigw.paziresh24.com/v1/search"
PAZIRESH24_BASE_URL = "https://www.paziresh24.com"
NOBAT_SEARCH_URL = "https://nobat.ir/118/?q="


def normalize_fa(value: str) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ").replace("\u200f", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def all_text(value) -> str:
    parts = []

    if isinstance(value, dict):
        for item in value.values():
            parts.append(all_text(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(all_text(item))
    elif value is not None:
        parts.append(str(value))

    return " ".join(part for part in parts if part)


def find_location_text(item: dict) -> str:
    preferred_keys = (
        "city",
        "city_name",
        "city_title",
        "town",
        "town_name",
        "province",
        "province_name",
        "address",
        "office_address",
        "clinic_address",
        "location",
        "locations",
        "centers",
        "center",
    )

    collected = []

    for key in preferred_keys:
        if key in item and item[key] is not None:
            collected.append(all_text(item[key]))

    return " ".join(x for x in collected if x).strip()


def make_nobat_booking_url(doctor_name: str) -> str:
    if not doctor_name:
        return ""
    return f"{NOBAT_SEARCH_URL}{quote(doctor_name)}"


@router.get("/")
def health_home():
    return {
        "status": "online",
        "module": "health"
    }


@router.get("/doctors/search")
def search_doctors(
        q: str = Query(default=""),
        city: str = Query(default="")
):
    query = q.strip()
    city_name = city.strip()

    if not query:
        return {
            "status": "error",
            "message": "عبارت جستجو خالی است.",
            "results": []
        }

    search_text = query
    if city_name:
        search_text = f"{query} {city_name}"

    try:
        response = requests.get(
            PAZIRESH24_SEARCH_URL,
            params={
                "text": search_text,
                "result_type": "فقط پزشکان"
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "AvaFamily/1.0"
            },
            timeout=20
        )

        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"خطا در ارتباط با منبع پزشکان: {exc}"
        )

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="پاسخ منبع پزشکان قابل خواندن نیست."
        )

    search_data = payload.get("search") or {}
    raw_results = search_data.get("result") or []

    wanted_city = normalize_fa(city_name)
    results = []

    for item in raw_results:

        if item.get("type") != "doctor":
            continue

        raw_item_text = normalize_fa(all_text(item))

        if wanted_city and wanted_city not in raw_item_text:
            continue

        doctor_name = item.get("title") or "نام ثبت نشده"
        location_text = city_name if city_name else find_location_text(item)

        profile_path = str(item.get("url") or "").strip()

        if profile_path.startswith("http://") or profile_path.startswith("https://"):
            paziresh24_url = profile_path
        elif profile_path:
            paziresh24_url = f"{PAZIRESH24_BASE_URL}{profile_path}"
        else:
            paziresh24_url = ""

        # اولویت نوبت‌گیری:
        # 1) Nobat.ir
        # 2) Paziresh24 fallback
        nobat_url = make_nobat_booking_url(doctor_name)
        booking_url = nobat_url or paziresh24_url
        booking_source = "nobat" if nobat_url else "paziresh24"

        results.append(
            {
                "id": str(item.get("id") or ""),
                "name": doctor_name,
                "specialty": (
                        item.get("display_expertise")
                        or "تخصص ثبت نشده"
                ),
                "satisfaction": int(item.get("satisfaction") or 0),
                "review_count": int(item.get("rates_count") or 0),
                "city": location_text,

                # source در UI برای نام منبع نوبت‌گیری استفاده می‌شود
                "source": booking_source,

                # منبع داده پزشک فعلاً پذیرش24 است
                "data_source": "paziresh24",

                "profile_path": profile_path,
                "booking_url": booking_url,
                "nobat_search_url": nobat_url,
                "paziresh24_url": paziresh24_url
            }
        )

    return {
        "status": "ok",
        "query": query,
        "city": city_name,
        "booking_priority": [
            "nobat",
            "paziresh24"
        ],
        "data_source": "paziresh24",
        "total": len(results),
        "results": results
    }
