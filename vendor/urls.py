from django.urls import path
from . import views     # <-- CORRECT


urlpatterns = [
    path('dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('products/', views.vendor_products, name='vendor_products'),
    path('products/add/', views.add_product, name='add_product'),
    path('product/edit/<int:product_id>/', views.edit_product, name='edit_product'),

    # path('products/edit/<int:pk>/', views.edit_product, name='edit_product'),
    path('products/delete/<int:pk>/', views.delete_product, name='delete_product'),

    path('orders/', views.vendor_orders, name='vendor_orders'),
    path('orders/<int:pk>/', views.order_detail, name='vendor_order_detail'),

    path('earnings/', views.vendor_earnings, name='vendor_earnings'),
    # path('earnings/request/', views.request_payout, name='vendor_request_payout'),

    path('reviews/', views.vendor_reviews, name='vendor_reviews'),
    path('settings/', views.vendor_settings, name='vendor_settings'),
    path('earnings/request/', views.vendor_request_payout, name='vendor_request_payout'),

]
