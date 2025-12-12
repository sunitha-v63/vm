# from django import template

# register = template.Library()

# @register.filter
# def avg_rating(reviews):
#     if not reviews:
#         return 0
#     total = sum(r.rating for r in reviews)
#     return round(total / len(reviews), 1)

from django import template
from django.db.models import Avg

register = template.Library()

@register.filter
def avg_rating(product):
    return product.reviews.aggregate(avg=Avg("rating"))["avg"] or 0
