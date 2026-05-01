from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import ContractorProfile

class ContractorRegistrationForm(UserCreationForm):
    # We make these fields required so we never get empty data
    email = forms.EmailField(required=True)
    company_name = forms.CharField(max_length=200, required=True)
    phone_number = forms.CharField(max_length=20, required=True)
    default_project_site = forms.CharField(
        max_length=200, 
        required=True, 
        label="Primary Project Location",
        widget=forms.TextInput(attrs={'placeholder': 'e.g., 5-Star, Mbuni Drive, Garden City, Nairobi'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        # 1. Save the basic User first
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        
        if commit:
            user.save()
            # 2. Update the Profile (which was auto-created by our signal)
            profile = user.contractor_profile
            profile.company_name = self.cleaned_data['company_name']
            profile.phone_number = self.cleaned_data['phone_number']
            profile.default_project_site = self.cleaned_data['default_project_site']
            profile.save()
            
        return user