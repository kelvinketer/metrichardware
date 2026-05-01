from django.contrib import admin
from django.core.mail import send_mail
from .models import Category, Product, QuoteRequest, ContractorProfile

# 1. Register Category
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

# 2. Register Product
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'base_price', 'unit_of_measure', 'requires_custom_dimensions', 'stock', 'is_active']
    list_filter = ['category', 'is_active', 'requires_custom_dimensions']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('base_price', 'stock', 'is_active') 

# 3. Register QuoteRequest (The Pricing Engine Dashboard)
@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    # UPDATED: Added vehicle_reg and updated_at to the list display
    list_display = ('id', 'customer_name', 'status', 'vehicle_reg', 'final_total', 'updated_at')
    
    # NEW: Allow quick status changes directly from the list view!
    list_editable = ('status',)
    
    list_filter = ('status', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'project_location', 'vehicle_reg')
    
    # Add updated_at to readonly fields so it doesn't crash the admin
    readonly_fields = ('created_at', 'updated_at', 'notes', 'cart_data', 'user')
    
    # UPDATED: Reorganized to include Financials and Logistics tracking
    fieldsets = (
        ('Contractor Details', {
            'fields': ('user', 'customer_name', 'customer_phone', 'project_location')
        }),
        ('Bill of Quantities (Read Only)', {
            'fields': ('notes', 'cart_data')
        }),
        ('Financials', {
            'fields': ('status', 'delivery_fee', 'final_total', 'is_paid', 'mpesa_receipt'),
            'description': "Set pricing, track M-Pesa receipts, and manage the order lifecycle."
        }),
        ('Logistics & Dispatch (Path A)', {
            'fields': ('driver_name', 'driver_phone', 'vehicle_reg'),
            'classes': ('collapse',), # This hides the section until you click to expand it
            'description': "Assign a vehicle and driver once the order is ready for transit."
        }),
    )

    # --- AUTOMATED ADMIN EMAILS & INVENTORY ORCHESTRATION ---
    def save_model(self, request, obj, form, change):
        if change: # If updating an existing quote
            try:
                old_obj = QuoteRequest.objects.get(id=obj.id)
                
                # 1. INVENTORY DEDUCTION: If it just crossed into 'invoiced' or 'paid'
                if old_obj.status not in ['invoiced', 'paid'] and obj.status in ['invoiced', 'paid']:
                    if obj.cart_data:
                        # Loop through every item in their cart
                        for item_id, item_data in obj.cart_data.items():
                            try:
                                product = Product.objects.get(id=int(item_id))
                                qty_ordered = int(item_data.get('quantity', 1))
                                
                                # Deduct the stock
                                product.stock = max(0, product.stock - qty_ordered)
                                product.save()

                                # LOW STOCK AUTOMATION TRIGGER
                                if product.stock < 10:
                                    alert_subject = f"URGENT: Low Stock Alert - {product.name}"
                                    alert_msg = f"System Alert,\n\nThe inventory for '{product.name}' at the Juja warehouse has dropped to {product.stock} units.\n\nPlease contact suppliers to restock immediately to fulfill future contractor requests."
                                    send_mail(alert_subject, alert_msg, 'system@metrichardware.co.ke', ['admin@metrichardware.co.ke'], fail_silently=True)

                            except (Product.DoesNotExist, ValueError):
                                pass

                # 2. CONTRACTOR NOTIFICATION EMAIL
                if old_obj.status != obj.status and obj.status in ['reviewed', 'invoiced', 'paid']:
                    if obj.user and obj.user.email:
                        subject = f"Metric Hardware - Quote Update (#BQ-{obj.id:04d})"
                        message = f"Hello {obj.customer_name},\n\nYour quote for the {obj.project_location} site has been updated to: {obj.get_status_display().upper()}.\n\nApproved Total: KES {obj.final_total or 'TBD'}\n\nPlease check your Contractor Dashboard to view the details or download your official PDF invoice.\n\nThank you,\nMetric Hardware Team"
                        send_mail(subject, message, 'sales@metrichardware.co.ke', [obj.user.email], fail_silently=True)
                        
            except QuoteRequest.DoesNotExist:
                pass
                    
        super().save_model(request, obj, form, change)

# 4. Register ContractorProfile (The Business Profile Dashboard)
@admin.register(ContractorProfile)
class ContractorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'role', 'parent', 'phone_number')
    list_editable = ('role',) # Easily change someone's role from the main list!
    list_filter = ('role', 'company_name')
    search_fields = ('company_name', 'user__username', 'user__email')
    
    # Make it easy to select the "Parent" company in the edit view
    raw_id_fields = ('parent',)