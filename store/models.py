from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User # <-- NEW: Import Django's secure User model
from django.db.models.signals import post_save # <-- NEW: For Profile creation
from django.dispatch import receiver # <-- NEW: For Profile creation

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Product(models.Model):
    UNIT_CHOICES = [
        ('piece', 'Per Piece'),
        ('sqm', 'Per Square Meter'),
        ('meter', 'Per Meter'),
    ]

    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    
    # NEW: Image field
    image = models.ImageField(upload_to='products/', blank=True, null=True, help_text="Upload a professional product photo")
    
    # Pricing and Units
    base_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in KES")
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES, default='piece')
    
    # Specialized Toggles
    requires_custom_dimensions = models.BooleanField(default=False, help_text="True for Glass & Boards cut to size")
    
    # Inventory
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class QuoteRequest(models.Model):
    """Handles custom B2B orders or fluctuating price checks"""
    
    # --- NEW: Expanded Lifecycle Statuses (Path A & B & C) ---
    STATUS_CHOICES = [
        ('draft', 'Draft (Not Submitted)'),  # <-- NEW: Draft state for multi-site carts
        ('pending', 'Pending Review'),
        ('reviewed', 'Price Quoted (Waiting for Approval)'),
        ('accepted', 'Approved by Contractor'),
        ('paid', 'Paid - Awaiting Dispatch'),
        ('loading', 'Loading at Warehouse'),
        ('dispatched', 'In Transit'),
        ('delivered', 'Delivered to Site'),
    ]

    # Link the quote to a registered user (allow null for guest checkouts)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='quotes')
    
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=15)
    project_location = models.CharField(max_length=200, help_text="Delivery site location")
    notes = models.TextField(blank=True, help_text="Bill of Quantities or custom dimensions")
    
    # The "Photographic Memory" for the 1-Click Reorder Engine
    cart_data = models.JSONField(default=dict, blank=True, help_text="Raw cart data for 1-click reorder")
    
    # 1. UPDATED: Expanded status choices
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # --- Admin Pricing Engine Fields ---
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Set by Admin in KES")
    final_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Final total including delivery")
    
    # --- NEW: Logistics & Dispatch Fields (Path A) ---
    driver_name = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    vehicle_reg = models.CharField(max_length=20, blank=True, verbose_name="Vehicle Plate Number")

    # --- M-Pesa Payment Tracking ---
    is_paid = models.BooleanField(default=False, help_text="True when M-Pesa webhook confirms payment")
    mpesa_receipt = models.CharField(max_length=50, blank=True, help_text="M-Pesa transaction code")
    
    # --- Date Tracking ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) # <-- NEW: Tracks last status change

    def __str__(self):
        return f"Quote #{self.id} - {self.customer_name}"


# --- CONTRACTOR PROFILE & TEAM MANAGEMENT (Path C) ---

class ContractorProfile(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Company Owner (Full Access)'),
        ('foreman', 'Site Foreman (Ordering & Drafts Only)'),
        ('accountant', 'Accountant (Billing & Payments Only)')
    ]

    # This links exactly one profile to one user
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='contractor_profile')
    
    company_name = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    default_project_site = models.CharField(max_length=200, blank=True)
    
    # --- NEW: TEAM MANAGEMENT FIELDS ---
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='owner')
    
    # If this is a sub-account, link it to the main owner's profile
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='team_members', help_text="Leave blank if this is the main owner account")

    def __str__(self):
        role_display = self.get_role_display()
        if self.parent:
            return f"{self.user.username} ({role_display}) - Team: {self.parent.company_name}"
        return f"{self.user.username} - {self.company_name} (Owner)"

    def get_company_quotes(self):
        """Fetches all quotes for the entire company, regardless of who submitted them."""
        from .models import QuoteRequest # Imported here to prevent circular import errors
        
        if self.parent:
            # I am a sub-account. Get the owner + all my siblings.
            team_users = [self.parent.user] + [p.user for p in self.parent.team_members.all()]
        else:
            # I am the owner. Get me + all my sub-accounts.
            team_users = [self.user] + [p.user for p in self.team_members.all()]
            
        return QuoteRequest.objects.filter(user__in=team_users).order_by('-updated_at')

# These signals automatically create and save the profile when a User is registered
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        ContractorProfile.objects.create(user=instance)

# Safety net added here!
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Check if the profile exists before trying to save it
    if hasattr(instance, 'contractor_profile'):
        instance.contractor_profile.save()