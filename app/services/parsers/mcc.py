DEFAULT_CATEGORY = "Інше"

TRANSFER_MCC_CODES: frozenset[int] = frozenset({4829, 6536, 6537, 6538})

# Grouped by canonical Ukrainian category labels aligned with UI badge & chart rules.
MCC_TO_CATEGORY: dict[int, str] = {
    # Продукти та супермаркети
    5411: "Продукти",  # Grocery stores, supermarkets (АТБ, Сільпо, Новус, Фора)
    5422: "Продукти",  # Meat & freezer provisions
    5441: "Продукти",  # Candy, nut, confectionery stores
    5451: "Продукти",  # Dairy products stores
    5462: "Продукти",  # Bakeries
    5499: "Продукти",  # Misc food stores / convenience markets
    5921: "Продукти",  # Package stores (beer, wine, liquor)

    # Кафе та ресторани
    5811: "Кафе та ресторани",  # Caterers
    5812: "Кафе та ресторани",  # Eating places, restaurants
    5813: "Кафе та ресторани",  # Bars, pubs, lounges
    5814: "Кафе та ресторани",  # Fast food (McDonald's, KFC, Пузата Хата)

    # Транспорт та таксі
    4111: "Транспорт",  # Local/suburban commuter transport
    4112: "Транспорт",  # Passenger railways (Укрзалізниця)
    4121: "Транспорт",  # Taxicabs and rideshares (Uklon, Bolt, Uber)
    4131: "Транспорт",  # Bus lines
    4511: "Транспорт",  # Airlines
    4784: "Транспорт",  # Tolls and bridge fees
    7523: "Транспорт",  # Parking lots and garages

    # Авто та пальне
    5511: "Авто та пальне",  # Car and truck dealers
    5532: "Авто та пальне",  # Automotive tire stores
    5533: "Авто та пальне",  # Automotive parts and accessories
    5541: "Авто та пальне",  # Service stations / fuel (ОККО, WOG, UPG)
    5542: "Авто та пальне",  # Automated fuel dispensers
    7538: "Авто та пальне",  # Automotive service shops (СТО)
    7542: "Авто та пальне",  # Car washes

    # Аптеки та медицина
    5122: "Аптеки та медицина",  # Drugs, drug proprietors
    5912: "Аптеки та медицина",  # Drug stores and pharmacies (АНЦ, Подорожник)
    5975: "Аптеки та медицина",  # Hearing aids
    5976: "Аптеки та медицина",  # Orthopedic goods
    8011: "Аптеки та медицина",  # Doctors / private clinics
    8021: "Аптеки та медицина",  # Dentists, orthodontists
    8062: "Аптеки та медицина",  # Hospitals
    8071: "Аптеки та медицина",  # Medical and dental labs (Сінево, Діла)
    8099: "Аптеки та медицина",  # Health practitioners / medical services

    # Комунальні, зв'язок та пошта
    4215: "Пошта та доставка",  # Courier services (Нова Пошта, Укрпошта)
    4812: "Комунальні та зв'язок",  # Telecommunication equipment
    4814: "Комунальні та зв'язок",  # Telecom services (Київстар, Vodafone, lifecell)
    4816: "Комунальні та зв'язок",  # Computer network / ISP services
    4899: "Комунальні та зв'язок",  # Cable, satellite, pay TV
    4900: "Комунальні та зв'язок",  # Utilities (electric, gas, water, heating)

    # Дім, ремонт та побут
    5200: "Дім та ремонт",  # Home supply warehouse stores (Епіцентр)
    5211: "Дім та ремонт",  # Lumber and building materials
    5251: "Дім та ремонт",  # Hardware stores
    5712: "Дім та ремонт",  # Furniture, home furnishings
    5977: "Побут та косметика",  # Cosmetic stores (Eva, Prostor, Watsons)
    7216: "Побут та косметика",  # Dry cleaners

    # Одяг та взуття
    5611: "Одяг та взуття",  # Men's clothing
    5621: "Одяг та взуття",  # Women's clothing
    5651: "Одяг та взуття",  # Family clothing
    5655: "Одяг та взуття",  # Sports and riding apparel
    5661: "Одяг та взуття",  # Shoe stores
    5691: "Одяг та взуття",  # Men's and women's clothing

    # Техніка та електроніка
    5045: "Техніка та електроніка",  # Computers, peripherals, software
    5722: "Техніка та електроніка",  # Household appliance stores
    5732: "Техніка та електроніка",  # Electronics stores (Rozetka, Comfy, Фокстрот)

    # Розваги, книги та підписки
    5815: "Розваги та підписки",  # Digital goods: media, books, movies, music
    5816: "Розваги та підписки",  # Digital goods: games (Steam)
    5817: "Розваги та підписки",  # Digital goods: applications (App Store, Google Play)
    5818: "Розваги та підписки",  # Digital goods: large digital vendors
    5942: "Розваги та підписки",  # Book stores (Yakaboo, Книгарня Є)
    5945: "Розваги та підписки",  # Hobby, toy, and game shops
    7832: "Розваги та підписки",  # Motion picture theaters
    7922: "Розваги та підписки",  # Theatrical producers / ticket agencies
    7997: "Спорт та фітнес",  # Membership clubs, gyms, fitness

    # Маркетплейси
    5311: "Маркетплейси",  # Department stores
    5399: "Маркетплейси",  # Misc general merchandise (Prom, Rozetka, AliExpress)

    # Банківські операції та перекази
    4829: "Перекази",  # Money transfer / P2P
    6011: "Зняття готівки",  # ATM cash withdrawals
    6012: "Банківські послуги",  # Financial institutions
    6536: "Перекази",  # MoneySend Intracountry
    6537: "Перекази",  # MoneySend Intercountry
    6538: "Перекази",  # MoneySend Funding
}


def resolve_mcc_category(mcc: int | None, fallback: str | None = None) -> str | None:
    """Resolves a numeric ISO 18245 MCC code to a canonical Ukrainian category."""
    if mcc is None:
        return fallback
    return MCC_TO_CATEGORY.get(int(mcc), fallback)