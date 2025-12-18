import re
import requests
from django.conf import settings
from core.models import Order
from .models import Conversation, Message

HF_HEADERS = {
    "Authorization": f"Bearer {settings.HF_API_KEY}",
    "Content-Type": "application/json",
}

STOPWORDS = {
    "what","is","are","the","in","of","and","to","me",
    "show","tell","please","any"
}

STORE_KEYWORDS = {
    "price","cost","buy","order","delivery",
    "cart","wishlist","offer","discount","available"
}

GREETINGS = {
    "morning": [
        "good morning", "gm", "morning"
    ],
    "afternoon": [
        "good afternoon", "good noon"
    ],
    "evening": [
        "good evening", "evening"
    ],
    "night": [
        "good night", "gn"
    ],
    "general": [
        "hi", "hello", "hey", "hai", "hii", "hola"
    ]
}

MEANINGLESS_WORDS = {"a", "an", "the"}

def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()

def clean_query(q):
    return " ".join(w for w in normalize(q).split() if w not in STOPWORDS)

def fix_article(text):
    return re.sub(r"\b(a)\s+([aeiou])", r"an \2", text)

def is_meaningless_input(query):
    q = normalize(query)
    return q in MEANINGLESS_WORDS or len(q) == 1

from difflib import SequenceMatcher

def match_product(query, products, threshold=0.75):
    q = normalize(query)
    best, score = None, 0

    for p in products:
        title = normalize(p.get("title", ""))

        if q == title or q in title:
            return p

        r = SequenceMatcher(None, q, title).ratio()
        if r > score:
            best, score = p, r

    return best if score >= threshold else None


def match_category(query, categories):
    q = normalize(query)

    for c in categories:
        name = normalize(c.get("name", ""))
        if q == name or q.rstrip("s") == name.rstrip("s"):
            return name

    for c in categories:
        name = normalize(c.get("name", ""))
        if q in name or name in q:
            return name

    return None

def related_products(category, products, limit=6):
    items = [
        p for p in products
        if p.get("category", "").lower() == category.lower()
    ]

    items.sort(key=lambda x: (
        x.get("stock", 0) <= 0,     
        not x.get("is_offer", False),  
        -x.get("rating", 0)
    ))

    return items[:limit]


def hf_generate(prompt, max_tokens=60):
    try:
        res = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers=HF_HEADERS,
            json={
                "model": settings.HF_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=15
        )
        return res.json()["choices"][0]["message"]["content"]
    except Exception:
        return ""

def product_benefit(name):
    return hf_generate(
        f"Give 1 short health benefit of {name}.",
        max_tokens=40
    )

def save_bot(conversation, user_msg, reply):
    bot = Message.objects.create(
        conversation=conversation,
        sender="bot",
        content=fix_article(reply)
    )
    return {
        "conversation_id": conversation.id,
        "user_message_id": user_msg.id,
        "bot_message_id": bot.id,
        "response": bot.content,
        "title": conversation.title,
    }

def get_category_url(category_name, categories):
    for c in categories:
        if normalize(c.get("name")) == normalize(category_name):
            return c.get("url")
    return "#"

def get_offer_products(products, category=None, product_name=None, limit=6):
    items = []

    for p in products:
        if not p.get("is_offer"):
            continue

        if product_name and normalize(product_name) not in normalize(p.get("title", "")):
            continue

        if category and normalize(p.get("category")) != normalize(category):
            continue

        items.append(p)

    items.sort(key=lambda x: (
        x.get("stock", 0) <= 0,
        -x.get("discount_percent", 0)
    ))

    return items[:limit]

def is_offer_query(query):
    q = normalize(query)
    return "offer" in q or "discount" in q or "sale" in q

def is_cart_query(query):
    q = normalize(query)
    return any(
        k in q for k in [
            "cart", "my cart", "show cart",
            "what in my cart", "items in cart"
        ]
    )

def is_wishlist_query(query):
    q = normalize(query)
    return any(
        k in q for k in [
            "wishlist", "wish list", "my wishlist",
            "show wishlist", "items in wishlist"
        ]
    )
    
def is_payment_query(query):
    q = normalize(query)
    return any(
        k in q for k in [
            "payment", "razorpay", "transaction",
            "payment status", "payment id"
        ]
    )

def is_tracking_query(query):
    q = normalize(query)
    return any(
        k in q for k in [
            "track order", "where is my order",
            "order location", "delivery status"
        ]
    )

def is_availability_query(query):
    q = normalize(query)
    return any(
        k in q for k in [
            "available", "in stock", "stock",
            "out of stock", "availability"
        ]
    )

def extract_order_id(query):
    q = query.lower()
    match = re.search(r"order\s*(id)?\s*[:#]?\s*(\d+)", q)
    if match:
        return int(match.group(2))

    return None

# --------related_products

def looks_like_grocery_word(query):
    q = query.strip()

    if not q.isalpha():
        return False

    if q[0].isupper():
        return False

    if len(q) > 20:
        return False

    return True

def build_category_vocabulary(products):
    """
    Builds a map like:
    {
      "fruits": {"apple", "orange", "grapes"},
      "vegetables": {"beans", "spinach"},
      ...
    }
    """
    vocab = {}

    for p in products:
        cat = p.get("category")
        title = normalize(p.get("title"))

        if not cat or not title:
            continue

        vocab.setdefault(cat, set()).add(title)

    return vocab

def infer_category_for_missing_product(query, products):
    q = normalize(query)

    if not looks_like_grocery_word(q):
        return None

    category_vocab = build_category_vocabulary(products)

    for category, words in category_vocab.items():
        for w in words:
            if q in w or w in q:
                return category

    return None


def ai_guess_category(word, categories):
    category_list = ", ".join(c.get("name") for c in categories)

    prompt = (
        f"Choose the most suitable category from this list ONLY:\n"
        f"{category_list}\n\n"
        f"Word: {word}\n\n"
        f"Rules:\n"
        f"- Return ONLY ONE category name from the list\n"
        f"- If not related to grocery or shopping, return 'none'\n"
        f"- Do not explain\n"
    )

    result = hf_generate(prompt, max_tokens=10).lower().strip()

    for c in categories:
        if normalize(c.get("name")) == normalize(result):
            return normalize(c.get("name"))

    return None

# -----diet

def detect_diet_type(query, product=None):
    if product:
        return None

    q = normalize(query)

    if any(w in q for w in {"morning", "breakfast"}):
        return "morning"

    if any(w in q for w in {"noon", "lunch", "afternoon"}):
        return "noon"

    if any(w in q for w in {"evening", "snack"}):
        return "evening"

    if any(w in q for w in {"night", "dinner"}):
        return "night"

    if "kids" in q and "noon" in q:
        return "kids_noon"

    if "kids" in q and "night" in q:
        return "kids_night"

    if "gym" in q and "morning" in q:
        return "gym_morning"

    if "gym" in q and "noon" in q:
        return "gym_noon"

    if "gym" in q and "night" in q:
        return "gym_night"

    if any(w in q for w in {"weight", "loss", "slim"}):
        return "weight_loss"

    if any(w in q for w in {"gym", "protein", "muscle"}):
        return "gym"

    if "kids" in q:
        return "kids"

    if any(w in q for w in {"diet", "nutrition"}):
        return "general"

    return None

DIET_CATEGORY_MAP = {
    "morning": ["fruits", "dairy", "eggs"],
    "weight_loss": ["fruits", "vegetables"],
    "gym": ["eggs", "meat", "nuts", "dairy"],
    "kids": ["fruits", "dairy", "eggs", "snacks"],
    "general": ["fruits", "vegetables", "nuts"]
}

DIET_INTRO = {
    "morning": "🥣 A healthy morning meal gives energy for the day.",
    "weight_loss": "🥗 For weight loss, light and fiber-rich foods are recommended.",
    "gym": "💪 For gym and muscle building, protein-rich foods help recovery.",
    "kids": "🧒 Kids need balanced nutrition for growth and energy.",
    "general": "🥗 A balanced diet supports overall health."
}

DIET_CATEGORY_MAP.update({
    "noon": ["vegetables", "dairy", "meat", "eggs"],
    "night": ["vegetables", "dairy"],
    "kids_morning": ["fruits", "dairy", "eggs"],
    "kids_evening": ["fruits", "snacks", "dairy"],
    "evening": ["snacks", "fruits", "nuts"],
    "gym_weight_loss": ["eggs", "vegetables", "nuts"]
})

DIET_INTRO.update({
    "noon": "🍽️ A balanced noon meal keeps energy steady throughout the day.",
    "night": "🌙 Light food at night helps digestion and improves sleep.",
    "kids_morning": "🧒🥣 A nutritious morning meal helps kids stay active and focused.",
    "kids_evening": "🧒🍎 Light and healthy evening snacks are best for kids.",
    "evening": "🌇 Light evening foods help digestion and prevent overeating.",
    "gym_weight_loss": "💪🥗 Protein-rich but low-fat foods support gym training and weight loss."
})

def is_general_health_query(query, product=None):
    if product:
        return False  # 🔴 IMPORTANT: product queries handled separately

    q = normalize(query)
    return any(k in q for k in {
        "health", "healthy",
        "nutritious", "good food"
    })


GENERAL_HEALTH_CATEGORIES = ["fruits", "vegetables", "nuts"]

def is_product_health_benefit_query(query):
    q = normalize(query)
    keywords = {
        "health benefit", "health benefits",
        "benefits", "good for health",
        "is it healthy", "nutrition"
    }
    return any(k in q for k in keywords)

def extract_context(raw, product, category):
    q = normalize(raw)

    return {
        "has_product": bool(product),
        "has_category": bool(category),
        "health_intent": any(w in q for w in {
            "health", "healthy", "benefit", "benefits",
            "nutrition", "good for"
        }),
        "diet_intent": any(w in q for w in {
            "diet", "weight", "loss", "gym",
            "kids", "breakfast", "morning"
        }),
    }

def detect_greeting(raw):
    raw = raw.lower()

    for time_of_day, phrases in GREETINGS.items():
        for p in phrases:
            if p in raw:
                return time_of_day

    return None

def greeting_reply(greeting_type):
    if greeting_type == "morning":
        return "🌅 Good morning! Hope you have a fresh and healthy day 😊"
    if greeting_type == "afternoon":
        return "☀️ Good afternoon! How can I help you today?"
    if greeting_type == "evening":
        return "🌆 Good evening! Looking for something fresh today?"
    if greeting_type == "night":
        return "🌙 Good night! Take care and eat healthy 🌿"

    return "👋 Hello! How can I help you today?"


def handle_chat(user, query, conversation=None, project_data=None):

    if not conversation:
        conversation = Conversation.objects.create(user=user)

    user_msg = Message.objects.create(
        conversation=conversation,
        sender="user",
        content=query
    )

    raw = normalize(query)
    clean = clean_query(raw)

    # ---------------- Greeting ----------------
    greeting_type = detect_greeting(raw)
    if greeting_type:
        return save_bot(
            conversation,
            user_msg,
            greeting_reply(greeting_type)
        )

    # ---------------- Meaningless input ----------------
    if is_meaningless_input(query):
        return save_bot(
            conversation,
            user_msg,
            "🙂 Please type a product or category name, for example: apple, milk, vegetables."
        )

    products = project_data.get("products", [])
    categories = project_data.get("categories", [])

    product = match_product(clean, products)
    category = match_category(clean, categories)
    
    #  CART

    if is_cart_query(raw):
        if user and user.is_authenticated:
            cart_items = user.cart_items.select_related("product")

            if not cart_items.exists():
                return save_bot(conversation, user_msg, "Your cart is empty 🛒")

            reply = "<b>🛒 Your cart items:</b><br>"
            for item in cart_items:
                reply += (
                    f"• {item.product.title} × {item.quantity} "
                    f"— ₹{item.product.base_price * item.quantity}<br>"
                )

            return save_bot(conversation, user_msg, reply)

        return save_bot(conversation, user_msg, "Please log in to view your cart 😊")
    
    #  WISHLIST

    if is_wishlist_query(raw):
        if user and user.is_authenticated:
            items = user.wishlist.all()

            if not items.exists():
                return save_bot(conversation, user_msg, "Your wishlist is empty ⭐")

            reply = "<b>⭐ Your wishlist items:</b><br>"
            for p in items:
                reply += f"• {p.title}<br>"

            return save_bot(conversation, user_msg, reply)

        return save_bot(conversation, user_msg, "Please log in to view wishlist 😊")

    #  OFFERS

    if is_offer_query(raw):
        if product:
            items = get_offer_products(products, product_name=product["title"])
        elif category:
            items = get_offer_products(products, category=category)
        else:
            items = get_offer_products(products)

        if items:
            reply = "<b>🔥 Available Offers:</b><br>"
            for p in items:
                status = (
                    "<span style='color:red'>Out of stock ❌</span>"
                    if p.get("stock", 0) <= 0
                    else f"<b>Offer: ₹{p['offer_price']}</b>"
                )
                reply += (
                    f"• <a href='{p.get('url','#')}' target='_blank'>{p['title']}</a><br>"
                    f"MRP: ₹{p['base_price']} | {status} ({p['discount_percent']}% OFF)<br><br>"
                )
            return save_bot(conversation, user_msg, reply)

        return save_bot(conversation, user_msg, "Currently there are no active offers 😔")
    
    # PRODUCT HEALTH BENEFITS

    if product and is_product_health_benefit_query(raw):
        benefit = product_benefit(product["title"])
        reply = (
            f"<b>🌿 Health benefits of "
            f"<a href='{product.get('url','#')}' target='_blank'>"
            f"{product['title']}</a>:</b><br>"
            f"{benefit}<br><br>"
            f"Price: ₹{product['base_price']}"
        )
        return save_bot(conversation, user_msg, reply)

    #  PRODUCT AVAILABILITY

    if product and is_availability_query(raw):
        if product.get("stock", 0) > 0:
            return save_bot(
                conversation,
                user_msg,
                f"✅ <b>{product['title']}</b> is available in stock.<br>"
                f"Price: ₹{product['base_price']}"
            )
        else:
            return save_bot(
                conversation,
                user_msg,
                f"❌ <b>{product['title']}</b> is currently out of stock."
            )

    #  PRODUCT DETAILS

    if product:
        price_text = (
            "<span style='color:red'>Out of stock ❌</span>"
            if product.get("stock", 0) <= 0
            else f"₹{product['base_price']}"
        )

        benefit = product_benefit(product["title"]) or (
        "Rich in nutrients and good for daily health."
        )
        image_url = product.get("image")  # DB image

        reply = (
            f"<b><a href='{product.get('url','#')}' target='_blank'>"
            f"{product['title']}</a></b><br>"
        )

        if image_url:
            reply += (
            f"<img src='{image_url}' "
            f"style='width:120px;border-radius:8px;margin:6px 0;'><br>"
        )
            
        reply += f"Price: {price_text}<br>🌿 {benefit}"
    
        return save_bot(conversation, user_msg, reply)
    
    # CATEGORY

    if category:
        items = related_products(category, products)
        if items:
            reply = f"<b>{category.title()} items available:</b><br>"
            for p in items:
                status = (
                    "<span style='color:red'>Out of stock ❌</span>"
                    if p.get("stock", 0) <= 0
                    else f"₹{p['base_price']}"
                )
                reply += (
                    f"• <a href='{p.get('url','#')}' target='_blank'>"
                    f"{p['title']}</a> — {status}<br>"
                )

            category_url = get_category_url(category, categories)
            if category_url and category_url != "#":
                reply += (
                    f"<br><a href='{category_url}' target='_blank'>"
                    f"View all {category.title()} items →</a>"
                )

            return save_bot(conversation, user_msg, reply)

    # DIET / NUTRITION

    diet_type = detect_diet_type(raw, product)
    if diet_type:
        allowed_categories = DIET_CATEGORY_MAP.get(diet_type, [])
        intro = DIET_INTRO.get(diet_type, "")
        suggested_products = [
            p for p in products
            if p.get("category") in allowed_categories and p.get("stock", 0) > 0
        ][:6]

        if suggested_products:
            reply = f"<b>{intro}</b><br><br>"
            for p in suggested_products:
                reply += (
                    f"• <a href='{p.get('url','#')}' target='_blank'>"
                    f"{p['title']}</a> — ₹{p['base_price']}<br>"
                )
            return save_bot(conversation, user_msg, reply)

    #  GENERAL HEALTH

    if is_general_health_query(raw, product):
        suggested_products = [
            p for p in products
            if p.get("category") in GENERAL_HEALTH_CATEGORIES and p.get("stock", 0) > 0
        ][:6]

        if suggested_products:
            reply = "<b>🥗 Foods that are good for health:</b><br><br>"
            for p in suggested_products:
                reply += (
                    f"• <a href='{p.get('url','#')}' target='_blank'>"
                    f"{p['title']}</a> — ₹{p['base_price']}<br>"
                )
            reply += (
                "<br><small>Tip: A balanced diet with fruits and vegetables "
                "helps maintain good health.</small>"
            )
            return save_bot(conversation, user_msg, reply)

    #  PRODUCT NOT FOUND → CATEGORY FALLBACK

    if not product and not category and looks_like_grocery_word(query):

        guessed_category = infer_category_for_missing_product(query, products)

        if not guessed_category:
            guessed_category = ai_guess_category(query, categories)

        if guessed_category:
            items = related_products(guessed_category, products)
            if items:
                reply = (
                    f"Sorry, we don’t have <b>{query}</b> right now ❌<br><br>"
                    f"<b>Available {guessed_category.title()} items:</b><br>"
                )
                for p in items:
                    reply += (
                        f"• <a href='{p.get('url','#')}' target='_blank'>"
                        f"{p['title']}</a> — ₹{p['base_price']}<br>"
                    )

                category_url = get_category_url(guessed_category, categories)
                if category_url and category_url != "#":
                    reply += (
                        f"<br><a href='{category_url}' target='_blank'>"
                        f"View all {guessed_category.title()} items →</a>"
                    )

                return save_bot(conversation, user_msg, reply)
            
    # ORDER / PAYMENT / TRACKING (RESTORED)

    if is_tracking_query(raw) or is_payment_query(raw) or "order" in raw:

        if not user or not user.is_authenticated:
            return save_bot(
                conversation,
                user_msg,
                "Please log in to view order details 🔐"
            )

        order_id = extract_order_id(raw)

        if order_id:
            o = Order.objects.filter(user=user, id=order_id).first()
            if not o:
                return save_bot(
                    conversation,
                    user_msg,
                    f"No order found with ID {order_id} ❌"
                )
        else:
            o = Order.objects.filter(user=user).order_by("-created_at").first()
            if not o:
                return save_bot(
                    conversation,
                    user_msg,
                    "You don’t have any orders yet 📦"
                )

        reply = (
            "<b>📦 Order Details</b><br>"
            f"Order ID: {o.id}<br>"
            f"Status: {o.status}<br>"
            f"Amount: ₹{o.total_amount}<br>"
        )

        if o.razorpay_payment_id:
            reply += f"Payment ID: {o.razorpay_payment_id}<br>"

        if o.expected_delivery_time:
            reply += f"Expected Delivery: {o.expected_delivery_time}<br>"

        return save_bot(conversation, user_msg, reply)

    #  FALLBACK
    return save_bot(
        conversation,
        user_msg,
        "👋 I’m your shopping assistant! "
        "Try asking: product price, today’s offers, my cart, or order status."
    )
