# mysite/imaging/forms.py
from django import forms

class GrayscaleForm(forms.Form):
    image = forms.ImageField()
    use_scipy = forms.BooleanField(required=False, initial=False)

class FilterForm(forms.Form):
    image = forms.ImageField()
    filter = forms.CharField(required=False,
                             help_text="9 integers separated by space")
    factor = forms.IntegerField(min_value=1, initial=1)
    use_scipy = forms.BooleanField(required=False, initial=False)
