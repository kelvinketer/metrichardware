from django.core.mail import send_mail
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Product, Category, QuoteRequest
from .cart import ProjectCart
from .forms import ContractorRegistrationForm

def store_home(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(category__name__icontains=query),
            is_active=True
        ).order_by('-created_at')
    else:
        products = Product.objects.filter(is_active=True).order_by('-created_at')

    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/product_grid.html', {'products': products})

    categories = Category.objects.all()
    context = {'products': products, 'categories': categories, 'query': query}
    return render(request, 'store/home.html', context)


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    cart = ProjectCart(request) 
    
    if request.method == 'POST':
        # ROLE GUARDRAIL: Accountants cannot order materials
        if request.user.is_authenticated and request.user.contractor_profile.role == 'accountant':
            messages.error(request, "Accountants cannot add items to the Project List. A Foreman or Owner must do this.")
            return redirect('store:product_detail', slug=product.slug)

        if product.stock <= 0:
            messages.error(request, f"Sorry, {product.name} is currently out of stock.")
            return redirect('store:product_detail', slug=product.slug)

        if product.requires_custom_dimensions:
            width = request.POST.get('width_mm')
            height = request.POST.get('height_mm')
            calc_total = request.POST.get('calculated_total')
            dimensions = f"{width}mm x {height}mm"
            cart.add(product=product, quantity=1, dimensions=dimensions, line_total=calc_total)
        else:
            quantity = int(request.POST.get('quantity', 1))
            if quantity > product.stock:
                messages.error(request, f"Cannot add {quantity}. We only have {product.stock} units of {product.name} remaining.")
                return redirect('store:product_detail', slug=product.slug)
                
            cart.add(product=product, quantity=quantity)

        messages.success(request, f"{product.name} successfully added to your Project List!")
        return redirect('store:home')

    return render(request, 'store/product_detail.html', {'product': product})


@login_required(login_url='store:login')
def project_list(request):
    profile = request.user.contractor_profile
    
    # ROLE GUARDRAIL: Accountants cannot view or submit the cart
    if profile.role == 'accountant':
        messages.error(request, "Accountants cannot create or submit BQs. Please ask a Foreman or Owner.")
        return redirect('store:dashboard')

    cart = ProjectCart(request)
    
    if request.method == 'POST':
        name = request.POST.get('customer_name')
        phone = request.POST.get('customer_phone')
        location = request.POST.get('project_location')
        action = request.POST.get('action') 
        
        bq_notes = "BILL OF QUANTITIES:\n"
        bq_notes += "=" * 40 + "\n"
        for item_id, item in cart.cart.items():
            if item.get('dimensions'):
                bq_notes += f"[{item['quantity']}x] {item['name']} | Size: {item['dimensions']} | KES {item['line_total']}\n"
            else:
                bq_notes += f"[{item['quantity']}x] {item['name']} | KES {item['line_total']}\n"
        
        bq_notes += "=" * 40 + "\n"
        bq_notes += f"GRAND TOTAL ESTIMATE: KES {cart.get_total()}\n"
        
        draft_id = request.session.get('active_draft_id')
        
        if draft_id:
            # UPDATED: Securely fetch draft using the shared company quotes
            quote = get_object_or_404(profile.get_company_quotes(), id=draft_id)
            quote.customer_name = name
            quote.customer_phone = phone
            quote.project_location = location
            quote.notes = bq_notes
            quote.cart_data = cart.cart
            quote.status = 'pending' if action == 'submit' else 'draft'
            quote.save()
        else:
            quote = QuoteRequest.objects.create(
                user=request.user,
                customer_name=name,
                customer_phone=phone,
                project_location=location,
                notes=bq_notes,
                cart_data=cart.cart,
                status='pending' if action == 'submit' else 'draft'
            )

        if action == 'save_draft':
            messages.info(request, f"Draft for '{location}' saved securely to your shared Dashboard.")
            cart.clear()
            if 'active_draft_id' in request.session:
                del request.session['active_draft_id']
            return redirect('store:dashboard')
            
        elif action == 'submit':
            if request.user.is_authenticated and request.user.email:
                subject = f"Metric Hardware - BQ Received (#BQ-{quote.id:04d})"
                message = f"Hello {name},\n\nWe have received your Bill of Quantities for the {location} site.\n\nOur logistics team is reviewing it and will assign a delivery fee shortly. You can track its status live on your Contractor Dashboard.\n\nThank you,\nMetric Hardware Team"
                send_mail(subject, message, 'sales@metrichardware.co.ke', [request.user.email], fail_silently=True)
            
            cart.clear()
            if 'active_draft_id' in request.session:
                del request.session['active_draft_id']
                
            messages.success(request, "BQ Submitted Successfully! Our logistics team is reviewing it now.")
            return redirect('store:home')

    return render(request, 'store/project_list.html', {'cart': cart})

# --- AUTHENTICATION VIEWS ---

def register_user(request):
    if request.method == 'POST':
        form = ContractorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) 
            messages.success(request, f"Corporate Account created! Welcome to Metric Hardware, {user.username}.")
            return redirect('store:home')
    else:
        form = ContractorRegistrationForm()
    return render(request, 'store/register.html', {'form': form})

def login_user(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                return redirect('store:home')
    else:
        form = AuthenticationForm()
    return render(request, 'store/login.html', {'form': form})

def logout_user(request):
    logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('store:home')


# --- CONTRACTOR DASHBOARD & TEAM HUB ---

@login_required(login_url='store:login')
def dashboard(request):
    # UPDATED: Fetch shared company quotes instead of just personal ones
    company_quotes = request.user.contractor_profile.get_company_quotes()
    return render(request, 'store/dashboard.html', {'quotes': company_quotes})

@login_required(login_url='store:login')
def reorder(request, quote_id):
    profile = request.user.contractor_profile
    
    # ROLE GUARDRAIL: Accountants shouldn't be editing drafts
    if profile.role == 'accountant':
        messages.error(request, "Accountants cannot edit drafts or reorder. Please ask a Foreman or Owner.")
        return redirect('store:dashboard')

    # UPDATED: Allow loading any cart from the shared company pool
    quote = get_object_or_404(profile.get_company_quotes(), id=quote_id)
    
    request.session['project_cart'] = quote.cart_data
    
    if quote.status == 'draft':
        request.session['active_draft_id'] = quote.id
        
    request.session.modified = True
    
    messages.success(request, f"Success! BQ-{quote.id:04d} loaded. You can modify quantities or submit immediately.")
    return redirect('store:project_list')

# --- INVOICE GENERATOR ---

@login_required(login_url='store:login')
def invoice_view(request, quote_id):
    # UPDATED: Allow any team member to view company invoices
    quote = get_object_or_404(request.user.contractor_profile.get_company_quotes(), id=quote_id)
    
    if quote.status == 'pending' or quote.status == 'draft':
        messages.warning(request, "This BQ is not ready for invoicing yet.")
        return redirect('store:dashboard')
        
    return render(request, 'store/invoice.html', {'quote': quote})

# --- NEGOTIATION ENGINE (Path B) ---

@login_required(login_url='store:login')
def accept_quote(request, quote_id):
    profile = request.user.contractor_profile
    
    # ROLE GUARDRAIL: Foremen cannot approve financial terms
    if profile.role == 'foreman':
        messages.error(request, "Foremen cannot approve pricing. Please ask an Owner or Accountant.")
        return redirect('store:dashboard')

    quote = get_object_or_404(profile.get_company_quotes(), id=quote_id)
    
    if quote.status == 'reviewed':
        quote.status = 'accepted'
        quote.save()
        messages.success(request, f"Quote #BQ-{quote.id:04d} accepted. You can now proceed to payment.")
    
    return redirect('store:dashboard')

# --- PAYMENT ENGINE ---

@login_required(login_url='store:login')
def trigger_mpesa_payment(request, quote_id):
    profile = request.user.contractor_profile
    
    # ROLE GUARDRAIL: Foremen cannot authorize payments
    if profile.role == 'foreman':
        messages.error(request, "Foremen cannot authorize payments. Please ask an Owner or Accountant.")
        return redirect('store:dashboard')

    quote = get_object_or_404(profile.get_company_quotes(), id=quote_id)
    
    if not quote.final_total or quote.is_paid:
        messages.error(request, "Invalid payment request.")
        return redirect('store:dashboard')

    phone = profile.phone_number
    amount = quote.final_total

    # SIMULATOR
    quote.is_paid = True
    quote.status = 'paid'
    quote.mpesa_receipt = f"MPESA{quote.id}XYZ987"
    quote.save()

    messages.success(request, f"STK Push sent to {phone} for KES {amount}. (SIMULATED SUCCESS: Marked as Paid!)")
    return redirect('store:dashboard')

# --- ADMIN COMMAND CENTER API (Path A) ---

@staff_member_required
def admin_analytics_api(request):
    revenue = QuoteRequest.objects.filter(
        status__in=['paid', 'loading', 'dispatched', 'delivered']
    ).aggregate(Sum('final_total'))['final_total__sum'] or 0
    
    outstanding = QuoteRequest.objects.filter(
        status='accepted', 
        is_paid=False
    ).aggregate(Sum('final_total'))['final_total__sum'] or 0
    
    pipeline = QuoteRequest.objects.values('status').annotate(count=Count('id'))
    
    return JsonResponse({
        'revenue': float(revenue),
        'outstanding': float(outstanding),
        'pipeline': list(pipeline)
    })