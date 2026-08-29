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

    value = str(value).strip().lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ").replace("\u200f", " ")
    value = re.sub(r"\s+", " ", value)

    return value


def all_text(value) -> str:
    """
    فقط برای بررسی داخلی نتیجه و فیلتر شهر استفاده می‌شود.
    خروجی این تابع هرگز به کارت اندروید فرستاده نمی‌شود.
    """
    parts = []

    if isinstance(value, dict):
        for item in value.values():
            text = all_text(item)
            if text:
                parts.append(text)

    elif isinstance(value, list):
        for item in value:
            text = all_text(item)
            if text:
                parts.append(text)

    elif value is not None:
        parts.append(str(value))

    return " ".join(parts)


def make_nobat_booking_url(
        doctor_name: str,
        city_name: str = ""
) -> str:

    doctor_name = str(doctor_name or "").strip()
    city_name = str(city_name or "").strip()

    if not doctor_name:
        return ""

    search_text = doctor_name

    if city_name:
        search_text = f"{doctor_name} {city_name}"

    return f"{NOBAT_SEARCH_URL}{quote(search_text)}"


def make_paziresh24_url(profile_path: str) -> str:

    profile_path = str(profile_path or "").strip()

    if not profile_path:
        return ""

    if profile_path.startswith("http://") or profile_path.startswith("https://"):
        return profile_path

    if not profile_path.startswith("/"):
        profile_path = "/" + profile_path

    return f"{PAZIRESH24_BASE_URL}{profile_path}"


def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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

        if not isinstance(item, dict):
            continue

        if item.get("type") != "doctor":
            continue

        # -------------------------------------------------
        # بررسی شهر فقط در داخل سرور
        # -------------------------------------------------

        if wanted_city:

            raw_item_text = normalize_fa(
                all_text(item)
            )

            if wanted_city not in raw_item_text:
                continue

        # -------------------------------------------------
        # اطلاعات تمیز پزشک
        # -------------------------------------------------

        doctor_id = str(
            item.get("id") or ""
        ).strip()

        doctor_name = str(
            item.get("title") or "نام ثبت نشده"
        ).strip()

        specialty = str(
            item.get("display_expertise")
            or "تخصص ثبت نشده"
        ).strip()

        satisfaction = safe_int(
            item.get("satisfaction")
        )

        review_count = safe_int(
            item.get("rates_count")
        )

        # -------------------------------------------------
        # لینک پذیرش24
        # -------------------------------------------------

        profile_path = str(
            item.get("url") or ""
        ).strip()

        paziresh24_url = make_paziresh24_url(
            profile_path
        )

        # -------------------------------------------------
        # لینک جستجوی نوبت.ir
        #
        # نوبت.ir اولویت نوبت‌گیری است.
        # اگر امکان ساخت لینک نبود، پذیرش24 استفاده می‌شود.
        # -------------------------------------------------

        nobat_url = make_nobat_booking_url(
            doctor_name=doctor_name,
            city_name=city_name
        )

        if nobat_url:
            booking_url = nobat_url
            source = "nobat"

        elif paziresh24_url:
            booking_url = paziresh24_url
            source = "paziresh24"

        else:
            booking_url = ""
            source = ""

        # -------------------------------------------------
        # خروجی مخصوص Ava Android
        #
        # هیچ address / center / UUID داخلی / location
        # یا اطلاعات خام دیگر ارسال نمی‌شود.
        # -------------------------------------------------

        results.append(
            {
                "id": doctor_id,
                "name": doctor_name,
                "specialty": specialty,

                # فقط همان شهری که کاربر جستجو کرده
                "city": city_name,

                "satisfaction": satisfaction,
                "review_count": review_count,

                # دقیقاً مطابق HealthScreen.kt
                "source": source,

                "booking_url": booking_url
            }
        )

    return {
        "status": "ok",
        "query": query,
        "city": city_name,
        "total": len(results),
        "results": results
    }