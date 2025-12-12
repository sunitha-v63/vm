from core.models import Product, Category, Order, DeliveryZone, Review


def get_project_data(user=None):
    """
    Loads all data from VetriMart models.
    Structured exactly the way api.py expects.
    """

    categories = [
        {
            "name": c.name,
            "count": c.product_count(),
            "url": c.get_absolute_url()
        }
        for c in Category.objects.all()
    ]

    products = []
    for p in Product.objects.all():
        title = p.title.lower()
        category = p.category.name.lower()

        products.append({
            "id": p.id,
            "title": p.title,
            "title_lower": title,     
            "category": category,
            "base_price": float(p.base_price),
            "offer_price": float(p.discounted_price),
            "is_offer": p.is_offer_active,
            "discount_percent": p.discount_percent,
            "rating": float(p.avg_rating),
            "stock": p.stock,
            "url": p.get_absolute_url(),

 
            "search_terms": [
                title,
                title.replace(" ", ""),
                category,
                category.replace(" ", ""),
            ]
        })


    offers = [
        {
            "title": p.title,
            "title_lower": p.title.lower(),
            "discount_percent": p.discount_percent,
            "price": float(p.discounted_price),
            "url": p.get_absolute_url()
        }
        for p in Product.objects.filter(is_offer=True)
    ]


    zones = [
        {
            "area": z.area_name,
            "pincode": z.pincode,
            "delay_hours": z.delivery_delay_hours
        }
        for z in DeliveryZone.objects.filter(is_active=True)
    ]

    reviews = [
        {
            "product": r.product.title,
            "rating": r.rating,
            "comment": r.comment
        }
        for r in Review.objects.all()
    ]


    orders = []
    if user and user.is_authenticated:
        orders = [
            {
                "id": o.id,
                "status": o.status,
                "eta": str(o.expected_delivery_time),
                "amount": float(o.total_amount)
            }
            for o in Order.objects.filter(user=user)
        ]

    return {
        "project": "VetriMart AI Assistant",

        "categories": categories,
        "products": products,
        "offers": offers,
        "delivery_zones": zones,
        "orders": orders,
        "reviews": reviews,

        "faq": {
            "return_policy": "Returns allowed within 7 days.",
            "refund_time": "Refund takes 3–5 business days.",
            "delivery_info": "Delivery takes 1–5 hours based on your zone.",
        }
    }
