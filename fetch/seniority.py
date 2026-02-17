"""
Seniority derivation from job titles.

Extracts seniority level from a job title string using pattern matching.
The TechMap CSV 'level' field (Engineer, Scientist, etc.) describes role TYPE,
not seniority — so we derive seniority separately from the title text.
"""

import re
from typing import Optional

# Patterns ordered by priority (first match wins)
SENIORITY_RULES = [
    # Intern / Student
    (r'\b(intern|internship|student|co[\-\s]?op|apprentice|trainee)\b', 'Intern'),

    # Junior / Entry-level
    (r'\b(junior|jr\.?|entry[\-\s]level|graduate|new\s+grad|associate)\b', 'Junior'),

    # Executive / C-level (check before Manager since "Head of" outranks manager)
    (r'\b(director|vp\b|vice[\-\s]president|cto|cfo|ceo|ciso|cpo|coo|cmo|cro|chief|head\s+of|evp|svp|gm\b|general\s+manager)\b', 'Executive'),

    # Lead / Principal / Staff
    (r'\b(lead|principal|staff|distinguished|founding|fellow|architect)\b', 'Lead'),

    # Manager
    (r'\b(manager|team[\-\s]lead|group[\-\s]lead|engineering[\-\s]manager|em\b)\b', 'Manager'),

    # Senior
    (r'\b(senior|sr\.?(?:\s|$))\b', 'Senior'),
]

# Compile patterns for performance
_COMPILED_RULES = [(re.compile(pattern, re.IGNORECASE), seniority) for pattern, seniority in SENIORITY_RULES]


def derive_seniority(title: str) -> str:
    """
    Derive seniority level from a job title.

    Args:
        title: Job title string (e.g., "Senior Backend Engineer")

    Returns:
        Seniority string: Intern, Junior, Mid-level, Senior, Lead, Manager, or Executive
    """
    if not title:
        return 'Mid-level'

    for pattern, seniority in _COMPILED_RULES:
        if pattern.search(title):
            return seniority

    return 'Mid-level'


# Hebrew city name to English mapping
CITY_MAP = {
    'תל אביב-יפו': 'Tel Aviv',
    'תל אביב - יפו': 'Tel Aviv',
    'תל-אביב-יפו': 'Tel Aviv',
    'תל אביב': 'Tel Aviv',
    'ירושלים': 'Jerusalem',
    'חיפה': 'Haifa',
    'באר שבע': 'Beer Sheva',
    'רעננה': "Ra'anana",
    'הרצליה': 'Herzliya',
    'פתח תקווה': 'Petah Tikva',
    'פתח תקוה': 'Petah Tikva',
    'רמת גן': 'Ramat Gan',
    'נתניה': 'Netanya',
    'כפר סבא': 'Kfar Saba',
    'מודיעין-מכבים-רעות': "Modi'in",
    'מודיעין': "Modi'in",
    'רחובות': 'Rehovot',
    'אשדוד': 'Ashdod',
    'ראשון לציון': 'Rishon LeZion',
    'הוד השרון': 'Hod HaSharon',
    'יקנעם עילית': "Yokne'am",
    'יקנעם': "Yokne'am",
    'לוד': 'Lod',
    'עכו': 'Acre',
    'נצרת': 'Nazareth',
    'קיסריה': 'Caesarea',
    'רמלה': 'Ramla',
    'בני ברק': 'Bnei Brak',
    'גבעתיים': "Giv'atayim",
    'אור יהודה': 'Or Yehuda',
    'קרית אונו': 'Kiryat Ono',
    'קרית גת': 'Kiryat Gat',
    'עפולה': 'Afula',
    'טבריה': 'Tiberias',
    'אילת': 'Eilat',
    'מגדל העמק': 'Migdal HaEmek',
    'צפת': 'Safed',
    'נהריה': 'Nahariya',
    'אריאל': 'Ariel',
    'שדרות': 'Sderot',
    'דימונה': 'Dimona',
    'ביתר עילית': 'Beitar Illit',
    'גבעת שמואל': "Giv'at Shmuel",
    'שוהם': 'Shoham',
    'יבנה': 'Yavne',
    'עתלית': 'Atlit',
    'Remote': 'Remote',
    'remote': 'Remote',
}


def translate_city(hebrew_city: str) -> str:
    """
    Translate a Hebrew city name to English.

    Args:
        hebrew_city: City name (Hebrew or English)

    Returns:
        English city name, or the original string if no translation found
    """
    if not hebrew_city:
        return 'Unknown'

    city = hebrew_city.strip()

    # Direct lookup
    if city in CITY_MAP:
        return CITY_MAP[city]

    # If it's already in ASCII (English), return as-is
    try:
        city.encode('ascii')
        return city
    except UnicodeEncodeError:
        pass

    # Return original if no translation
    return city


# ─── Israeli Location Detection ──────────────────────────────────────────────

# Known Israeli cities in English (lowercase for matching)
_ISRAELI_CITIES = {
    'tel aviv', 'tel-aviv', 'jerusalem', 'haifa', 'beer sheva', 'be\'er sheva',
    'ra\'anana', 'raanana', 'herzliya', 'petah tikva', 'ramat gan',
    'netanya', 'kfar saba', 'modi\'in', 'rehovot', 'ashdod',
    'rishon lezion', 'hod hasharon', 'yokne\'am', 'lod', 'acre',
    'nazareth', 'caesarea', 'ramla', 'bnei brak', 'giv\'atayim',
    'or yehuda', 'kiryat ono', 'kiryat gat', 'afula', 'tiberias',
    'eilat', 'migdal haemek', 'safed', 'nahariya', 'ariel', 'sderot',
    'dimona', 'beitar illit', 'giv\'at shmuel', 'shoham', 'yavne',
    'atlit', 'nes ziona', 'rosh haayin', 'rosh ha\'ayin', 'ramat hasharon',
    'holon', 'bat yam', 'givatayim', 'kinneret',
}

_ISRAELI_KEYWORDS = {'israel', 'gush dan', 'tel aviv district'}


def is_israeli_location(location: str) -> bool:
    """
    Check whether a location string refers to an Israeli location.
    Returns True for Israeli cities, 'Israel' mentions, Hebrew text,
    Remote/Hybrid (no location), and empty strings.
    """
    if not location or not location.strip():
        return True

    loc = location.strip().lower()

    # Remote/Hybrid without a specific country = keep
    # But "Remote US", "Remote, Germany" etc = not Israeli
    if loc in ('remote', 'hybrid', 'unknown'):
        return True

    # Hebrew characters = Israeli
    if any('\u0590' <= c <= '\u05FF' for c in loc):
        return True

    # Check for 'Israel' keyword
    for kw in _ISRAELI_KEYWORDS:
        if kw in loc:
            return True

    # Multi-location strings (Greenhouse uses "; " separator)
    # Consider it Israeli if ANY part is Israeli
    parts = [p.strip() for p in loc.replace(';', ',').split(',')]
    for part in parts:
        part_clean = part.strip().lower()
        for city in _ISRAELI_CITIES:
            if city in part_clean:
                return True

    return False


# ─── Department Normalization ────────────────────────────────────────────────

# Standard TechMap department categories
STANDARD_DEPARTMENTS = {
    'admin', 'business', 'data-science', 'design', 'devops', 'finance',
    'frontend', 'hardware', 'hr', 'legal', 'marketing',
    'procurement-operations', 'product', 'project-management', 'qa',
    'sales', 'security', 'software', 'support',
}

# Mapping from ATS department names to standard categories
_DEPARTMENT_MAP = {
    # Engineering / R&D
    'engineering': 'software',
    'r&d': 'software',
    'research and development': 'software',
    'technology': 'software',
    'development': 'software',
    'backend': 'software',
    'fullstack': 'software',
    'full stack': 'software',
    'platform': 'software',
    'infrastructure': 'software',
    'mobile': 'software',
    'algorithms': 'software',
    'system': 'software',
    'automation': 'qa',
    'reversing': 'security',
    # Frontend
    'front end': 'frontend',
    'front-end': 'frontend',
    'ui': 'frontend',
    'ux': 'design',
    # Product
    'product management': 'product',
    # Sales / GTM
    'go-to-market (gtm)': 'sales',
    'go-to-market': 'sales',
    'gtm': 'sales',
    'pre sales': 'sales',
    'pre-sales': 'sales',
    'business development': 'sales',
    # Customer-facing
    'customer success': 'support',
    'customer support': 'support',
    'customer experience': 'support',
    'customers operations': 'support',
    'professional services': 'support',
    # Operations
    'operations': 'procurement-operations',
    'supply chain': 'procurement-operations',
    'strategy & operations': 'procurement-operations',
    'strategic projects': 'procurement-operations',
    'delivery': 'procurement-operations',
    # People / HR
    'people': 'hr',
    'talent': 'hr',
    'recruiting': 'hr',
    # IT
    'it': 'devops',
    'information technology': 'devops',
    # Finance
    'accounting': 'finance',
    'cfo': 'finance',
    # C-suite / general
    'cto': 'software',
    'g&a': 'admin',
    'general & administrative': 'admin',
}


def normalize_department(raw_dept: str) -> str:
    """
    Normalize an ATS department name to a standard TechMap category.
    Strips numeric prefixes like '301-engineering' → 'engineering' first.
    Returns empty string if no mapping found.
    """
    if not raw_dept:
        return ''

    dept = raw_dept.strip().lower()

    # Already standard
    if dept in STANDARD_DEPARTMENTS:
        return dept

    # Strip numeric prefix (e.g., "301-engineering" → "engineering")
    stripped = re.sub(r'^\d+[\-\s]+', '', dept)
    if stripped in STANDARD_DEPARTMENTS:
        return stripped

    # Look up in mapping
    if dept in _DEPARTMENT_MAP:
        return _DEPARTMENT_MAP[dept]
    if stripped in _DEPARTMENT_MAP:
        return _DEPARTMENT_MAP[stripped]

    # Substring matching as fallback (try stripped version too)
    for candidate in (dept, stripped):
        for key, value in _DEPARTMENT_MAP.items():
            if key in candidate:
                return value

    # Final fallback: check if any standard department name appears in the string
    for std in STANDARD_DEPARTMENTS:
        if std in dept or std in stripped:
            return std

    return ''


if __name__ == '__main__':
    # Quick test
    test_titles = [
        'Senior Backend Engineer',
        'Junior Product Designer',
        'VP of Engineering',
        'Staff Software Engineer',
        'Machine Learning Engineer',
        'Engineering Manager',
        'Head of Data Science',
        'Intern - Software Development',
        'Principal Architect',
        'Full Stack Developer',
        'Sr. DevOps Engineer',
        'CTO',
        'Team Lead - Frontend',
        'Graduate Software Engineer',
    ]

    for title in test_titles:
        print(f'{title:40s} → {derive_seniority(title)}')
