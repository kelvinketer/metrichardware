import time

class ProjectCart:
    def __init__(self, request):
        """Initialize the cart securely inside the user's browser session"""
        self.session = request.session
        cart = self.session.get('project_cart')
        if not cart:
            # Save an empty dictionary in the session if no cart exists
            cart = self.session['project_cart'] = {}
        self.cart = cart

    def add(self, product, quantity=1, dimensions=None, line_total=None):
        """Add a product or custom glass panel to the BQ"""
        # Generate a unique timestamp ID so a user can add multiple glass panels of different sizes
        item_id = str(int(time.time() * 1000)) 
        
        self.cart[item_id] = {
            'product_id': product.id,
            'name': product.name,
            'quantity': int(quantity),
            'dimensions': dimensions,
            'line_total': float(line_total) if line_total else float(product.base_price) * int(quantity)
        }
        self.save()

    def save(self):
        """Mark the session as modified to make sure it saves"""
        self.session.modified = True

    def get_total(self):
        """Calculate the Grand Total of the entire project list"""
        return sum(item['line_total'] for item in self.cart.values())

    def clear(self):
        """Empty the cart after a successful checkout"""
        del self.session['project_cart']
        self.save()