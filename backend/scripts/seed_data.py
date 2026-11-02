"""
Seed the database with:
  1. The first SUPER_ADMIN user (from settings, so it's not hardcoded).
  2. A realistic mock e-commerce dataset: categories baked into products,
     500 products, 1000 customers, 10,000+ events.

Customers behave like real shoppers (a few favourite categories and brands,
session funnels view -> cart -> checkout -> purchase, and "bundle" purchases
such as laptop + laptop bag), so the recommendation engine has real patterns
to learn from.

Run with:
    python -m scripts.seed_data            # seed what is missing (users, products, events, customers, offers)
    python -m scripts.seed_data --reset    # wipe products/customers/events and re-seed
"""
import argparse
import asyncio
import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.database.database import AsyncSessionLocal
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, Platform, UserEvent
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog
from app.database.models.user import User, UserRole
from app.customers.service import recompute_profiles
from app.database.models.experiment import Experiment, ExperimentExposure
from app.database.models.offer import Offer, OfferInteraction, OfferRedemption
from app.experiments import engine as experiment_engine
from app.offers import engine as offer_engine

configure_logging()
logger = get_logger("seed")
fake = Faker()

CATEGORIES = [
    "Running Shoes", "Casual Shoes", "Formal Shoes", "Sneakers", "Sandals",
    "T-Shirts", "Shirts", "Jeans", "Jackets", "Activewear",
    "Laptops", "Smartphones", "Headphones", "Smartwatches", "Cameras",
    "Laptop Bags", "Phone Cases", "Memory Cards", "Chargers", "Power Banks",
    "Backpacks", "Wallets", "Sunglasses", "Watches", "Belts",
    "Kitchen Appliances", "Home Decor", "Furniture", "Lighting", "Bedding",
    "Skincare", "Haircare", "Makeup", "Fragrances", "Grooming",
    "Books", "Stationery", "Toys", "Sports Equipment", "Fitness Gear",
    "Socks", "Caps", "Scarves", "Gloves", "Umbrellas",
    "Board Games", "Musical Instruments", "Art Supplies", "Pet Supplies", "Garden Tools",
]

BRANDS = [
    "Nike", "Adidas", "Puma", "Reebok", "Levi's", "Zara", "H&M",
    "Apple", "Samsung", "Sony", "Dell", "HP", "Lenovo", "Bose",
    "Fossil", "Ray-Ban", "IKEA", "Philips", "Nivea", "L'Oreal",
]

# Product pairs that make sense as "frequently bought together"
FBT_CATEGORY_PAIRS = [
    ("Laptops", "Laptop Bags"),
    ("Cameras", "Memory Cards"),
    ("Running Shoes", "Socks"),
    ("Smartphones", "Phone Cases"),
    ("Smartphones", "Chargers"),
]
PRIMARY_CATEGORIES = {a for a, _ in FBT_CATEGORY_PAIRS}

NUM_PRODUCTS = 500
NUM_CUSTOMERS = 1000
MIN_EVENTS = 15000
BUNDLE_SESSIONS = 160
PLATFORMS = [Platform.WEB, Platform.MOBILE, Platform.ANDROID, Platform.IOS]
TAGS = ["bestseller", "new-arrival", "trending", "limited-edition", "eco-friendly"]


async def seed_admin(db) -> None:
    existing = await db.execute(select(User).where(User.role == UserRole.SUPER_ADMIN))
    if existing.scalars().first() is not None:
        logger.info("seed_admin_skipped", reason="super admin already exists")
        return

    admin = User(
        email=settings.FIRST_SUPER_ADMIN_EMAIL,
        hashed_password=hash_password(settings.FIRST_SUPER_ADMIN_PASSWORD),
        full_name="Super Admin",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    logger.info("seed_admin_created", email=settings.FIRST_SUPER_ADMIN_EMAIL)


async def seed_demo_staff(db) -> None:
    """Two extra staff accounts so the Users screen and role permissions can be tried out (same password as the admin)."""
    demo = [
        ("marketing@example.com", "Maya Marketing", UserRole.MARKETING_MANAGER),
        ("viewer@example.com", "Vik Viewer", UserRole.VIEWER),
    ]
    for email, name, role in demo:
        if (await db.execute(select(User.id).where(User.email == email))).first() is None:
            db.add(User(email=email, hashed_password=hash_password(settings.FIRST_SUPER_ADMIN_PASSWORD),
                        full_name=name, role=role, is_active=True))
    await db.commit()


async def reset_catalog_and_events(db) -> None:
    for model in (RecommendationLog, UserEvent, EcommerceCustomer, Product, Offer, Experiment):  # offers / experiments cascade to their stats
        await db.execute(delete(model))
    await db.commit()
    logger.info("seed_reset_done")


async def seed_products(db) -> list[Product]:
    existing = await db.execute(select(Product))
    products = existing.scalars().all()
    if products:
        logger.info("seed_products_skipped", count=len(products))
        return list(products)

    products = []
    for i in range(NUM_PRODUCTS):
        category = CATEGORIES[i % len(CATEGORIES)]  # exactly 10 products per category
        brand = random.choice(BRANDS)
        singular = category[:-1] if category.endswith("s") else category
        name = f"{brand} {fake.word().capitalize()} {singular}"
        products.append(
            Product(
                external_product_id=f"PROD_{1000 + i}",
                name=name,
                description=f"{name}: {fake.sentence(nb_words=14)}",
                category=category,
                brand=brand,
                price=round(random.uniform(199, 89999), 2),
                rating=round(random.uniform(3.0, 5.0), 1),
                tags=random.sample(TAGS, k=random.randint(0, 2)),
                in_stock=random.random() > 0.15,
                is_active=random.random() > 0.02,
                attributes={"color": fake.color_name()},
            )
        )

    db.add_all(products)
    await db.commit()
    for p in products:
        await db.refresh(p)
    logger.info("seed_products_created", count=len(products))
    return products


def _event(event_type, user_id, product, session_id, platform, when, metadata=None) -> UserEvent:
    product_id = product.external_product_id if product is not None else None
    raw = f"{event_type.value}|{user_id}|{product_id}|{session_id}|{when.isoformat()}|{uuid.uuid4()}"
    return UserEvent(
        external_user_id=user_id,
        event_type=event_type,
        product_id=product_id,
        session_id=session_id,
        platform=platform,
        event_metadata=metadata or ({"category": product.category} if product is not None else {}),
        occurred_at=when,
        idempotency_key=hashlib.sha256(raw.encode()).hexdigest(),
    )


def generate_events(products: list[Product]) -> list[UserEvent]:
    """Funnel sessions driven by per-customer tastes, plus guaranteed bundle purchases."""
    now = datetime.now(timezone.utc)
    by_category: dict[str, list[Product]] = {}
    for p in products:
        by_category.setdefault(p.category, []).append(p)
    categories = sorted(by_category)

    # Every product in a "primary" category has one preferred complement (its usual accessory).
    partner: dict[tuple[str, str], Product] = {}
    for primary, secondary in FBT_CATEGORY_PAIRS:
        for p in by_category.get(primary, []):
            partner[(p.external_product_id, secondary)] = random.choice(by_category[secondary])

    def complement(p: Product, secondary: str) -> Product:
        if random.random() < 0.75:
            return partner[(p.external_product_id, secondary)]
        return random.choice(by_category[secondary])

    customer_ids = [f"USER_{10000 + i}" for i in range(NUM_CUSTOMERS)]
    tastes = {
        uid: {
            "categories": random.sample(categories, k=random.randint(2, 3)),
            "brand": random.choice(BRANDS),
        }
        for uid in customer_ids
    }

    # Real shops have a few power users and many casual ones: this is what makes RFM segments interesting.
    activity = {uid: random.choices(["power", "regular", "casual"], weights=[15, 30, 55])[0] for uid in customer_ids}
    session_weight = {"power": 8, "regular": 3, "casual": 1}
    weights = [session_weight[activity[uid]] for uid in customer_ids]

    def pick(uid: str) -> Product:
        taste = tastes[uid]
        cat = random.choice(taste["categories"]) if random.random() < 0.8 else random.choice(categories)
        pool = by_category[cat]
        favourite = [p for p in pool if p.brand == taste["brand"]]
        return random.choice(favourite) if favourite and random.random() < 0.4 else random.choice(pool)

    def session_start() -> datetime:
        # skewed towards recent days so popularity/decay have something to show
        days = random.triangular(0, 90, 0)
        return now - timedelta(days=days, minutes=random.randint(30, 600))

    events: list[UserEvent] = []

    session_no = 0
    while len(events) < MIN_EVENTS or session_no < len(customer_ids):
        # first pass gives every customer at least one session
        uid = customer_ids[session_no] if session_no < len(customer_ids) else random.choices(customer_ids, weights=weights)[0]
        session_no += 1
        sid = f"SESSION_{uuid.uuid4().hex[:12]}"
        platform = random.choice(PLATFORMS)
        t = session_start()
        cart: list[Product] = []

        def add(event_type, product=None, metadata=None):
            nonlocal t
            t += timedelta(seconds=random.randint(20, 240))
            events.append(_event(event_type, uid, product, sid, platform, t, metadata))

        first = pick(uid)
        add(EventType.CATEGORY_VIEW, first)
        if random.random() < 0.25:
            add(EventType.PRODUCT_SEARCH, None, {"query": first.category.lower()})

        for _ in range(random.randint(1, 5)):
            product = first if not events or random.random() < 0.3 else pick(uid)
            add(EventType.PRODUCT_VIEW, product)
            if random.random() < 0.08:
                add(EventType.RECOMMENDATION_VIEW, pick(uid), {"algorithm": "hybrid"})
                if random.random() < 0.2:
                    add(EventType.RECOMMENDATION_CLICK, pick(uid), {"algorithm": "hybrid"})
            if random.random() < 0.12:
                add(EventType.WISHLIST_ADD, product)
            cart_chance = 0.45 if product.category in PRIMARY_CATEGORIES else 0.22
            if random.random() < cart_chance:
                add(EventType.ADD_TO_CART, product)
                cart.append(product)
                if random.random() < 0.1:
                    add(EventType.REMOVE_FROM_CART, product)
                    cart.pop()

        if cart and random.random() < 0.6:
            add(EventType.CHECKOUT_STARTED, None)
            bought = list(cart)
            for item in cart:
                for primary, secondary in FBT_CATEGORY_PAIRS:
                    if item.category == primary and random.random() < 0.5:
                        extra = complement(item, secondary)
                        add(EventType.ADD_TO_CART, extra)
                        bought.append(extra)
            for item in {p.external_product_id: p for p in bought}.values():
                quantity = random.choices([1, 2, 3], weights=[85, 10, 5])[0]
                add(EventType.PURCHASE, item, {"category": item.category, "quantity": quantity})
            if random.random() < 0.04:
                add(EventType.RETURN, bought[0])
            elif random.random() < 0.03:
                add(EventType.PURCHASE_CANCELLED, bought[0])
            if random.random() < 0.15:
                add(EventType.PRODUCT_REVIEW, bought[0])

    # Guaranteed bundle sessions: primary + its usual accessory, bought together.
    for _ in range(BUNDLE_SESSIONS):
        primary_cat, secondary_cat = random.choice(FBT_CATEGORY_PAIRS)
        uid = random.choice(customer_ids)
        sid = f"SESSION_{uuid.uuid4().hex[:12]}"
        platform = random.choice(PLATFORMS)
        t = session_start()
        main_product = random.choice(by_category[primary_cat])
        accessory = complement(main_product, secondary_cat)
        for event_type, product in [
            (EventType.PRODUCT_VIEW, main_product),
            (EventType.ADD_TO_CART, main_product),
            (EventType.PRODUCT_VIEW, accessory),
            (EventType.ADD_TO_CART, accessory),
            (EventType.CHECKOUT_STARTED, None),
            (EventType.PURCHASE, main_product),
            (EventType.PURCHASE, accessory),
        ]:
            t += timedelta(seconds=random.randint(20, 240))
            events.append(_event(event_type, uid, product, sid, platform, t))

    return events


async def seed_events_and_customers(db, products: list[Product]) -> None:
    existing_events = (await db.execute(select(UserEvent.id).limit(1))).scalar_one_or_none()
    existing_customers = (await db.execute(select(EcommerceCustomer.id).limit(1))).scalar_one_or_none()
    if existing_events is not None or existing_customers is not None:
        logger.info("seed_events_skipped", reason="events/customers already exist (use --reset)")
        return

    events = generate_events(products)

    seen: dict[str, tuple[datetime, datetime]] = {}
    for e in events:
        first, last = seen.get(e.external_user_id, (e.occurred_at, e.occurred_at))
        seen[e.external_user_id] = (min(first, e.occurred_at), max(last, e.occurred_at))
    db.add_all(
        EcommerceCustomer(external_user_id=uid, first_seen_at=first, last_seen_at=last)
        for uid, (first, last) in seen.items()
    )
    await db.commit()
    logger.info("seed_customers_created", count=len(seen))

    for start in range(0, len(events), 1000):
        db.add_all(events[start : start + 1000])
        await db.commit()
    logger.info("seed_events_created", count=len(events))


def _sample_offers(now: datetime) -> list[dict]:
    """A realistic mix: active campaigns per segment plus a draft, a paused, an expired and an ended one."""
    return [
        dict(code="WELCOME10", name="Welcome - 10% off your next order", offer_type="percent_off", value=10,
             target_segments=["new_customer", "prospect"], priority=70, status="active", ends_at=now + timedelta(days=60),
             description="A friendly nudge for first-time and not-yet-buying visitors."),
        dict(code="VIP15", name="VIP thank-you - 15% off", offer_type="percent_off", value=15, max_discount=5000,
             target_segments=["champions", "loyal"], priority=80, status="active", max_per_customer=2,
             description="Reward your best customers. Discount capped at 5,000."),
        dict(code="COMEBACK20", name="We miss you - 20% off", offer_type="percent_off", value=20, max_discount=3000,
             target_segments=["at_risk", "cant_lose", "hibernating", "about_to_sleep"], priority=90, status="active",
             max_redemptions=200, ends_at=now + timedelta(days=30), description="Win-back campaign with a budget of 200 redemptions."),
        dict(code="FREESHIP", name="Free shipping over 999", offer_type="free_shipping", min_order_value=999,
             priority=40, status="active", max_per_customer=3, ends_at=now + timedelta(days=20),
             description="Open to everyone."),
        dict(code="LAPTOP5K", name="5,000 off laptops", offer_type="fixed_off", value=5000, min_order_value=40000,
             target_categories=["Laptops"], priority=60, status="active", max_redemptions=100,
             description="Fixed discount on laptop orders above 40,000."),
        dict(code="BACK12", name="Come back - 12% off", offer_type="percent_off", value=12,
             target_segments=["need_attention", "potential_loyalist"], priority=65, status="active",
             ends_at=now + timedelta(days=2), description="Ends in two days - shows the urgency boost."),
        dict(code="SUMMER25", name="Summer sale - 25% off (draft)", offer_type="percent_off", value=25, max_discount=8000,
             priority=50, status="draft", description="Not live yet."),
        dict(code="FLASH30", name="Flash sale - 30% off (paused)", offer_type="percent_off", value=30, max_discount=6000,
             target_segments=["loyal", "champions"], priority=75, status="paused", description="Paused by marketing."),
        dict(code="EXPIRED15", name="Festive 15% (expired)", offer_type="percent_off", value=15, priority=50,
             status="active", starts_at=now - timedelta(days=60), ends_at=now - timedelta(days=5),
             description="Ran its course - shows as expired."),
        dict(code="OLDBYE5", name="Goodbye 5% (ended)", offer_type="percent_off", value=5, priority=30,
             status="ended", starts_at=now - timedelta(days=90), ends_at=now - timedelta(days=40)),
    ]


async def seed_offers(db) -> None:
    """Sample campaigns with believable impressions, clicks and redemptions."""
    if (await db.execute(select(Offer.id).limit(1))).scalar_one_or_none() is not None:
        logger.info("seed_offers_skipped", reason="offers already exist")
        return

    now = datetime.now(timezone.utc)
    offers = []
    for spec in _sample_offers(now):
        spec.setdefault("starts_at", now - timedelta(days=45))
        offers.append(Offer(created_by=settings.FIRST_SUPER_ADMIN_EMAIL, **spec))
    db.add_all(offers)
    await db.commit()

    customers = (
        await db.execute(select(EcommerceCustomer.external_user_id, EcommerceCustomer.segment))
    ).all()
    by_segment: dict[str | None, list[str]] = {}
    for uid, segment in customers:
        by_segment.setdefault(segment, []).append(uid)
    everyone = [uid for uid, _ in customers]

    interactions: list[OfferInteraction] = []
    redemptions: list[OfferRedemption] = []
    for offer in offers:
        if offer.status == "draft":
            continue
        pool = [uid for seg in offer.target_segments for uid in by_segment.get(seg, [])] if offer.target_segments else everyone
        if not pool:
            continue
        audience = random.sample(pool, k=min(len(pool), max(10, int(len(pool) * 0.6)), 300))
        window_end = offer.ends_at if offer.ends_at and offer.ends_at < now else now
        window_days = max(1.0, (window_end - offer.starts_at).total_seconds() / 86400)
        redeemed_users: set[str] = set()
        for index, uid in enumerate(audience):
            shown_at = offer.starts_at + timedelta(days=random.uniform(0, window_days))
            interactions.append(OfferInteraction(
                offer_id=offer.id, external_user_id=uid, action="impression", occurred_at=shown_at))
            if random.random() > 0.24:
                continue
            interactions.append(OfferInteraction(
                offer_id=offer.id, external_user_id=uid, action="click",
                occurred_at=shown_at + timedelta(minutes=random.randint(1, 90))))
            if random.random() > 0.28 or uid in redeemed_users:
                continue
            if offer.max_redemptions is not None and sum(1 for r in redemptions if r.offer_id == offer.id) >= offer.max_redemptions:
                continue
            floor = float(offer.min_order_value or 800)
            order_value = round(random.uniform(floor, floor + 40000), 2)
            discount, free_shipping = offer_engine.compute_discount(offer_engine.OfferRule(
                id=str(offer.id), code=offer.code, name=offer.name, offer_type=offer.offer_type,
                value=float(offer.value), status=offer.status,
                max_discount=float(offer.max_discount) if offer.max_discount is not None else None), order_value)
            redeemed_users.add(uid)
            redemptions.append(OfferRedemption(
                offer_id=offer.id, external_user_id=uid, order_ref=f"SEED-{offer.code}-{index}",
                order_value=order_value, discount_amount=discount, free_shipping=free_shipping,
                redeemed_at=shown_at + timedelta(hours=random.randint(1, 48))))

    for start in range(0, len(interactions), 1000):
        db.add_all(interactions[start : start + 1000])
        await db.commit()
    db.add_all(redemptions)
    await db.commit()
    logger.info("seed_offers_created", offers=len(offers), interactions=len(interactions), redemptions=len(redemptions))


async def seed_experiments(db) -> None:
    """Three sample A/B tests: a running one, a finished one with a clear winner, and a draft."""
    if (await db.execute(select(Experiment.id).limit(1))).scalar_one_or_none() is not None:
        logger.info("seed_experiments_skipped", reason="experiments already exist")
        return

    now = datetime.now(timezone.utc)
    products = (await db.execute(select(Product).where(Product.is_active.is_(True), Product.in_stock.is_(True)))).scalars().all()
    customer_ids = [uid for (uid,) in (await db.execute(select(EcommerceCustomer.external_user_id))).all()]

    running = Experiment(
        key="reco-hybrid-vs-content", name="Homepage recommendations: hybrid vs content-based", kind="recommendations",
        description="Does the blended engine beat pure content similarity?", hypothesis="The hybrid blend converts better.",
        primary_metric="conversion", traffic_percent=60, status="running", started_at=now - timedelta(days=14),
        variants=[{"key": "control", "name": "Hybrid (current)", "weight": 50, "config": {"strategy": "hybrid"}},
                  {"key": "content", "name": "Content-based only", "weight": 50, "config": {"strategy": "content"}}],
        created_by=settings.FIRST_SUPER_ADMIN_EMAIL)
    finished = Experiment(
        key="winback-offer-test", name="Win-back: COMEBACK20 vs no offer", kind="offers",
        description="Holdout test of the win-back coupon.", hypothesis="A 20% offer brings lapsed customers back.",
        primary_metric="conversion", traffic_percent=100, status="completed", started_at=now - timedelta(days=45),
        ended_at=now - timedelta(days=20), winner_key="comeback",
        variants=[{"key": "control", "name": "No offer (holdout)", "weight": 50, "config": {"offer_codes": []}},
                  {"key": "comeback", "name": "COMEBACK20", "weight": 50, "config": {"offer_codes": ["COMEBACK20"]}}],
        created_by=settings.FIRST_SUPER_ADMIN_EMAIL)
    draft = Experiment(
        key="popular-vs-personalised", name="Popular vs personalised picks", kind="recommendations",
        description="Not started yet.", primary_metric="click", traffic_percent=30, status="draft",
        variants=[{"key": "control", "name": "Hybrid (current)", "weight": 50, "config": {"strategy": "hybrid"}},
                  {"key": "popular", "name": "Popular only", "weight": 50, "config": {"strategy": "popular"}}],
        created_by=settings.FIRST_SUPER_ADMIN_EMAIL)
    db.add_all([running, finished, draft])
    await db.commit()

    exposures: list[ExperimentExposure] = []
    for customer in customer_ids:  # running test: real assignment rule, real outcomes (the seeded behaviour is random, so no winner)
        variant = experiment_engine.assign(running.key, running.traffic_percent, running.variants, customer)
        if variant:
            exposures.append(ExperimentExposure(experiment_id=running.id, external_user_id=customer, variant_key=variant,
                                                first_exposed_at=running.started_at + timedelta(days=random.uniform(0, 13))))

    # finished test: DEMO outcomes - the offer variant buys more (24% vs 10%), written as extra purchase events
    extra_events: list[UserEvent] = []
    for customer in random.sample(customer_ids, k=min(len(customer_ids), 400)):
        variant = experiment_engine.assign(finished.key, finished.traffic_percent, finished.variants, customer)
        if variant is None:
            continue
        exposed_at = finished.started_at + timedelta(days=random.uniform(0, 10))
        exposures.append(ExperimentExposure(experiment_id=finished.id, external_user_id=customer, variant_key=variant, first_exposed_at=exposed_at))
        if products and random.random() < (0.24 if variant == "comeback" else 0.10):
            product = random.choice(products)
            when = exposed_at + timedelta(days=random.uniform(0.1, 9))
            session = f"SESSION_{uuid.uuid4().hex[:12]}"
            extra_events.append(_event(EventType.PURCHASE, customer, product, session, Platform.WEB, when,
                                       {"category": product.category, "quantity": 1, "source": "seed_experiment"}))
    db.add_all(exposures)
    db.add_all(extra_events)
    await db.commit()
    logger.info("seed_experiments_created", experiments=3, exposures=len(exposures), extra_purchases=len(extra_events))


async def main(reset: bool) -> None:
    random.seed(42)
    Faker.seed(42)
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
        await seed_demo_staff(db)
        if reset:
            await reset_catalog_and_events(db)
        products = await seed_products(db)
        await seed_events_and_customers(db, products)
        summary = await recompute_profiles(db)
        if summary:
            logger.info("seed_profiles_computed", segments=summary["segments"])
        await seed_offers(db)
        await seed_experiments(db)
        await recompute_profiles(db)  # the demo experiment purchases change spend / segments
        try:
            from app.ml.service import rebuild_ml_models
            ml_summary = await rebuild_ml_models(db)
            logger.info("seed_ml_models_built", models=len(ml_summary.get("models", [])))
        except Exception as exc:
            logger.warning("seed_ml_rebuild_failed", error=str(exc))
    logger.info("seed_complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the database with mock data")
    parser.add_argument("--reset", action="store_true", help="delete products, customers and events first")
    args = parser.parse_args()
    asyncio.run(main(args.reset))
