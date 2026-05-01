from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    # Catalog & Shopping
    path('', views.store_home, name='home'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('project-list/', views.project_list, name='project_list'),
    
    # User Authentication & Portal
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reorder/<int:quote_id>/', views.reorder, name='reorder'),
    path('invoice/<int:quote_id>/', views.invoice_view, name='invoice'),
    path('pay/<int:quote_id>/', views.trigger_mpesa_payment, name='pay'), 
    path('accept-quote/<int:quote_id>/', views.accept_quote, name='accept_quote'),
    
    # --- ADMIN COMMAND CENTER (Path A) ---
    path('api/admin-analytics/', views.admin_analytics_api, name='admin_analytics_api'),
]