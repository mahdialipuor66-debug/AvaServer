from fastapi import APIRouter, Query, HTTPException
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse
import re
import requests


router = APIRouter(
    prefix="/health",
    tags=["Health"]
)


PAZIRESH24_SEARCH_URL = "https://apigw.paziresh24.com/v1/search"
PAZIRESH24_BASE_URL = "https://www.paziresh24.com"

NOBAT_SEARCH_URL = "https://nobat.ir/118/"


CITY_KEYS = {
    "city",
    "city_name",
    "city_title",
    "town",
    "town_name",
}


PROVINCE_KEYS = {
    "province",
    "province_name",
    "province_title",
    "state",
    "state_name",
}


IRAN_PROVINCES = {
    "آذربایجان شرقی",
    "آذربایجان غربی",
    "اردبیل",
    "اصفهان",
    "البرز",
    "ایلام",
    "بوشهر",
    "تهران",
    "چهارمحال و بختیاری",
    "خراسان جنوبی",
    "خراسان رضوی",
    "خراسان شمالی",
    "خوزستان",
    "زنجان",
    "سمنان",
    "سیستان و بلوچستان",
    "فارس",
    "قزوین",
    "قم",
    "کردستان",
    "کرمان",
    "کرمانشاه",
    "کهگیلویه و بویراحمد",
    "گلستان",
    "گیلان",
    "لرستان",
    "مازندران",
    "مرکزی",
    "هرمزگان",
    "همدان",
    "یزد",
}


def normalize_fa(value: str) -> str:

    if not value:
        return ""

    value = str(value).strip().lower()

    value = (
        value
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ۀ", "ه")
        .replace("ة", "ه")
    )

    value = (
        value
        .replace("\u200c", " ")
        .replace("\u200f", " ")
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value


def normalize_location(value: str) -> str:

    value = normalize_fa(value)

    for prefix in (
            "استان ",
            "شهرستان ",
            "شهر ",
    ):

        if value.startswith(prefix):

            value = value[
                len(prefix):
            ].strip()

    return value


def normalize_doctor_name(
        value: str
) -> str:

    value = normalize_fa(value)

    value = re.sub(
        r"^(دکتر|دكتر|پزشک|doctor|dr\.?)\s+",
        "",
        value,
        flags=re.IGNORECASE
    )

    return value.strip()


def safe_int(value) -> int:

    try:
        return int(value or 0)

    except (
            TypeError,
            ValueError
    ):
        return 0


def clean_named_values(
        value
) -> list[str]:

    values = []

    if isinstance(
            value,
            dict
    ):

        for key in (
                "name",
                "title"
        ):

            item = value.get(key)

            if item is not None:

                text = str(
                    item
                ).strip()

                if text:
                    values.append(text)

    elif isinstance(
            value,
            list
    ):

        for item in value:

            values.extend(
                clean_named_values(
                    item
                )
            )

    elif value is not None:

        text = str(
            value
        ).strip()

        if text:
            values.append(text)

    return values


def first_value_for_keys(
        data: dict,
        allowed_keys: set[str]
) -> str:

    for key, value in data.items():

        normalized_key = str(
            key
        ).strip().lower()

        if (
                normalized_key
                not in allowed_keys
        ):
            continue

        values = clean_named_values(
            value
        )

        if values:
            return values[0]

    return ""


def is_virtual_center(
        data: dict
) -> bool:

    center_type = str(
        data.get(
            "center_type"
        ) or ""
    ).strip()

    if center_type == "3":
        return True

    center_name = normalize_fa(
        data.get("name")
        or data.get("title")
        or ""
    )

    if (
            "ویزیت آنلاین" in center_name
            and
            "پذیرش24" in center_name
    ):
        return True

    return False


def extract_location_records(
        value
) -> list[dict]:

    records = []

    def walk(node):

        if isinstance(
                node,
                dict
        ):

            if is_virtual_center(
                    node
            ):
                return

            city_name = (
                first_value_for_keys(
                    node,
                    CITY_KEYS
                )
            )

            province_name = (
                first_value_for_keys(
                    node,
                    PROVINCE_KEYS
                )
            )

            if (
                    city_name
                    or province_name
            ):

                records.append(
                    {
                        "city": city_name,
                        "province": province_name
                    }
                )

            for item in (
                    node.values()
            ):

                if isinstance(
                        item,
                        (
                                dict,
                                list
                        )
                ):

                    walk(item)

        elif isinstance(
                node,
                list
        ):

            for item in node:
                walk(item)

    walk(value)

    unique = []
    seen = set()

    for record in records:

        city_normalized = (
            normalize_location(
                record["city"]
            )
        )

        province_normalized = (
            normalize_location(
                record["province"]
            )
        )

        key = (
            city_normalized,
            province_normalized
        )

        if not any(key):
            continue

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            record
        )

    return unique


def make_paziresh24_url(
        profile_path: str
) -> str:

    profile_path = str(
        profile_path or ""
    ).strip()

    if not profile_path:
        return ""

    if (
            profile_path.startswith(
                "http://"
            )
            or
            profile_path.startswith(
                "https://"
            )
    ):
        return profile_path

    if not profile_path.startswith(
            "/"
    ):
        profile_path = (
                "/" + profile_path
        )

    return (
        f"{PAZIRESH24_BASE_URL}"
        f"{profile_path}"
    )


def make_nobat_search_url(
        doctor_name: str,
        city_name: str
) -> str:

    doctor_name = str(
        doctor_name or ""
    ).strip()

    city_name = str(
        city_name or ""
    ).strip()

    if not doctor_name:
        return ""

    search_text = doctor_name

    if city_name:

        search_text = (
            f"{doctor_name} "
            f"{city_name}"
        )

    return (
        f"{NOBAT_SEARCH_URL}"
        f"?q={quote(search_text)}"
    )


class NobatLinkParser(
    HTMLParser
):

    def __init__(self):

        super().__init__()

        self.links = []

        self._href = None

        self._text_parts = []

    def handle_starttag(
            self,
            tag,
            attrs
    ):

        if tag.lower() != "a":
            return

        self._href = ""

        for key, value in attrs:

            if key.lower() == "href":

                self._href = (
                        value or ""
                )

                break

        self._text_parts = []

    def handle_data(
            self,
            data
    ):

        if self._href is not None:

            self._text_parts.append(
                data
            )

    def handle_endtag(
            self,
            tag
    ):

        if (
                tag.lower() == "a"
                and
                self._href is not None
        ):

            self.links.append(
                (
                    self._href,
                    " ".join(
                        self._text_parts
                    )
                )
            )

            self._href = None

            self._text_parts = []


class PageTextParser(
    HTMLParser
):

    def __init__(self):

        super().__init__()

        self.parts = []

    def handle_data(
            self,
            data
    ):

        text = str(
            data or ""
        ).strip()

        if text:

            self.parts.append(
                text
            )

    def get_text(
            self
    ) -> str:

        return " ".join(
            self.parts
        )


def is_direct_nobat_profile_url(
        url: str
) -> bool:

    try:

        parsed = urlparse(url)

    except ValueError:

        return False

    host = (
        parsed.netloc
        .lower()
        .split(":")[0]
    )

    if host not in {
        "nobat.ir",
        "www.nobat.ir"
    }:
        return False

    path = (
        parsed.path
        .strip("/")
    )

    if not path:
        return False

    if "/" in path:
        return False

    reserved_paths = {
        "118",
        "login",
        "register",
        "about",
        "contact",
        "blog",
        "faq",
        "privacy",
        "terms",
        "search"
    }

    if path.lower() in reserved_paths:
        return False

    return True


def nobat_profile_matches(
        profile_url: str,
        doctor_name: str,
        city_name: str
) -> bool:

    try:

        response = requests.get(
            profile_url,
            headers={
                "Accept":
                    "text/html,"
                    "application/xhtml+xml",

                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; "
                    "Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 "
                    "Safari/537.36"
            },
            timeout=6,
            allow_redirects=True
        )

        response.raise_for_status()

    except requests.RequestException:

        return False

    parser = PageTextParser()

    try:

        parser.feed(
            response.text
        )

    except Exception:

        return False

    page_text = normalize_fa(
        parser.get_text()
    )

    doctor_normalized = (
        normalize_doctor_name(
            doctor_name
        )
    )

    city_normalized = (
        normalize_location(
            city_name
        )
    )

    if not doctor_normalized:
        return False

    if (
            doctor_normalized
            not in page_text
    ):
        return False

    if (
            city_normalized
            and
            city_normalized
            not in page_text
    ):
        return False

    return True


@lru_cache(
    maxsize=512
)
def find_verified_nobat_profile(
        doctor_name: str,
        city_name: str
) -> str:

    doctor_name = str(
        doctor_name or ""
    ).strip()

    city_name = str(
        city_name or ""
    ).strip()

    if (
            not doctor_name
            or
            not city_name
    ):
        return ""

    doctor_normalized = (
        normalize_doctor_name(
            doctor_name
        )
    )

    if not doctor_normalized:
        return ""

    search_url = (
        make_nobat_search_url(
            doctor_name=doctor_name,
            city_name=city_name
        )
    )

    try:

        response = requests.get(
            search_url,
            headers={
                "Accept":
                    "text/html,"
                    "application/xhtml+xml",

                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; "
                    "Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 "
                    "Safari/537.36"
            },
            timeout=6,
            allow_redirects=True
        )

        response.raise_for_status()

    except requests.RequestException:

        return ""

    parser = NobatLinkParser()

    try:

        parser.feed(
            response.text
        )

    except Exception:

        return ""

    checked_urls = set()

    for (
            href,
            link_text
    ) in parser.links:

        absolute_url = urljoin(
            "https://nobat.ir/",
            href
        )

        if not (
                is_direct_nobat_profile_url(
                    absolute_url
                )
        ):
            continue

        if (
                absolute_url
                in checked_urls
        ):
            continue

        link_doctor_normalized = (
            normalize_doctor_name(
                link_text
            )
        )

        if (
                doctor_normalized
                not in
                link_doctor_normalized
        ):
            continue

        checked_urls.add(
            absolute_url
        )

        if nobat_profile_matches(
                profile_url=absolute_url,
                doctor_name=doctor_name,
                city_name=city_name
        ):

            return absolute_url

    return ""


def select_display_city(
        locations: list[dict],
        requested_location: str,
        requested_is_province: bool
) -> str:

    wanted = normalize_location(
        requested_location
    )

    if wanted:

        if requested_is_province:

            for location in locations:

                province_name = (
                    normalize_location(
                        location[
                            "province"
                        ]
                    )
                )

                city_name = str(
                    location[
                        "city"
                    ] or ""
                ).strip()

                if (
                        province_name
                        == wanted
                        and
                        city_name
                ):
                    return city_name

        else:

            for location in locations:

                city_name = str(
                    location[
                        "city"
                    ] or ""
                ).strip()

                if (
                        normalize_location(
                            city_name
                        )
                        == wanted
                ):
                    return city_name

    for location in locations:

        city_name = str(
            location[
                "city"
            ] or ""
        ).strip()

        if city_name:
            return city_name

    return ""


def location_matches(
        locations: list[dict],
        requested_location: str,
        requested_is_province: bool,
        requested_is_known_city: bool
) -> bool:

    wanted = normalize_location(
        requested_location
    )

    if not wanted:
        return True

    if requested_is_province:

        return any(
            normalize_location(
                location[
                    "province"
                ]
            )
            == wanted

            for location
            in locations
        )

    if requested_is_known_city:

        return any(
            normalize_location(
                location[
                    "city"
                ]
            )
            == wanted

            for location
            in locations
        )

    return True


def resolve_booking(
        doctor: dict
) -> dict:

    nobat_url = (
        find_verified_nobat_profile(
            doctor_name=doctor["name"],
            city_name=doctor["city"]
        )
    )

    if nobat_url:

        doctor["source"] = "nobat"

        doctor[
            "booking_url"
        ] = nobat_url

        return doctor

    paziresh24_url = doctor.get(
        "_paziresh24_url",
        ""
    )

    if paziresh24_url:

        doctor[
            "source"
        ] = "paziresh24"

        doctor[
            "booking_url"
        ] = paziresh24_url

    else:

        doctor[
            "source"
        ] = ""

        doctor[
            "booking_url"
        ] = ""

    return doctor


@router.get("/")
def health_home():

    return {
        "status": "online",
        "module": "health"
    }


@router.get(
    "/doctors/search"
)
def search_doctors(
        q: str = Query(
            default=""
        ),
        city: str = Query(
            default=""
        )
):

    query = q.strip()

    requested_location = (
        city.strip()
    )

    if not query:

        return {
            "status": "error",
            "message":
                "عبارت جستجو خالی است.",
            "results": []
        }

    search_text = query

    if requested_location:

        search_text = (
            f"{query} "
            f"{requested_location}"
        )

    try:

        response = requests.get(
            PAZIRESH24_SEARCH_URL,
            params={
                "text":
                    search_text,

                "result_type":
                    "فقط پزشکان"
            },
            headers={
                "Accept":
                    "application/json",

                "User-Agent":
                    "AvaFamily/1.0"
            },
            timeout=20
        )

        response.raise_for_status()

        payload = (
            response.json()
        )

    except requests.RequestException as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "خطا در ارتباط "
                "با منبع پزشکان: "
                f"{exc}"
            )
        )

    except ValueError:

        raise HTTPException(
            status_code=502,
            detail=(
                "پاسخ منبع پزشکان "
                "قابل خواندن نیست."
            )
        )

    search_data = (
            payload.get(
                "search"
            )
            or {}
    )

    raw_results = (
            search_data.get(
                "result"
            )
            or []
    )

    doctor_items = []

    for item in raw_results:

        if not isinstance(
                item,
                dict
        ):
            continue

        if (
                item.get("type")
                != "doctor"
        ):
            continue

        doctor_items.append(
            {
                "item": item,

                "locations":
                    extract_location_records(
                        item
                    )
            }
        )

    wanted_location = (
        normalize_location(
            requested_location
        )
    )

    normalized_province_names = {
        normalize_location(
            item
        )
        for item
        in IRAN_PROVINCES
    }

    requested_is_province = (
            wanted_location
            in normalized_province_names
    )

    all_result_cities = {

        normalize_location(
            location["city"]
        )

        for doctor
        in doctor_items

        for location
        in doctor["locations"]

        if normalize_location(
            location["city"]
        )
    }

    requested_is_known_city = (
            bool(
                wanted_location
            )
            and
            not requested_is_province
            and
            wanted_location
            in all_result_cities
    )

    results = []

    for doctor_data in doctor_items:

        item = doctor_data[
            "item"
        ]

        locations = doctor_data[
            "locations"
        ]

        if not location_matches(
                locations=locations,
                requested_location=
                requested_location,
                requested_is_province=
                requested_is_province,
                requested_is_known_city=
                requested_is_known_city
        ):
            continue

        doctor_id = str(
            item.get("id")
            or ""
        ).strip()

        doctor_name = str(
            item.get("title")
            or "نام ثبت نشده"
        ).strip()

        specialty = str(
            item.get(
                "display_expertise"
            )
            or
            "تخصص ثبت نشده"
        ).strip()

        satisfaction = safe_int(
            item.get(
                "satisfaction"
            )
        )

        review_count = safe_int(
            item.get(
                "rates_count"
            )
        )

        doctor_city = (
            select_display_city(
                locations=
                locations,

                requested_location=
                requested_location,

                requested_is_province=
                requested_is_province
            )
        )

        profile_path = str(
            item.get("url")
            or ""
        ).strip()

        paziresh24_url = (
            make_paziresh24_url(
                profile_path
            )
        )

        results.append(
            {
                "id":
                    doctor_id,

                "name":
                    doctor_name,

                "specialty":
                    specialty,

                "city":
                    doctor_city,

                "satisfaction":
                    satisfaction,

                "review_count":
                    review_count,

                "source":
                    "",

                "booking_url":
                    "",

                "_paziresh24_url":
                    paziresh24_url
            }
        )

    if results:

        workers = min(
            5,
            len(results)
        )

        with ThreadPoolExecutor(
                max_workers=workers
        ) as executor:

            results = list(
                executor.map(
                    resolve_booking,
                    results
                )
            )

    for doctor in results:

        doctor.pop(
            "_paziresh24_url",
            None
        )

    return {
        "status": "ok",
        "query": query,
        "city": requested_location,
        "total": len(results),
        "results": results
    }