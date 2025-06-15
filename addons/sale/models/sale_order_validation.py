from odoo import _
from odoo.exceptions import ValidationError

class SaleOrderValidation:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def _check_prepayment_percent(self):
        for order in self.order:
            if order.require_payment and not (0 < order.prepayment_percent <= 1.0):
                raise ValidationError(_("Prepayment percentage must be a valid percentage."))
    
    def _check_order_line_company_id(self):
        for order in self.order:
            invalid_companies = order.order_line.product_id.company_id.filtered(
                lambda c: order.company_id not in c._accessible_branches()
            )
            if invalid_companies:
                bad_products = order.order_line.product_id.filtered(
                    lambda p: p.company_id and p.company_id in invalid_companies
                )
                raise ValidationError(_(
                    "Your quotation contains products from company %(product_company)s whereas your quotation belongs to company %(quote_company)s. \n Please change the company of your quotation or remove the products from other companies (%(bad_products)s).",
                    product_company=', '.join(invalid_companies.sudo().mapped('display_name')),
                    quote_company=order.company_id.display_name,
                    bad_products=', '.join(bad_products.mapped('display_name')),
                ))
    
    def _check_loyalty_points_used(self):
        for order in self.order:
            if order.loyalty_points_used < 0:
                raise ValidationError("The number of loyalty_points_used can't be negative.")
    
    def _check_loyalty_points(self):
        for order in self.order:
            if order.loyalty_points < 0:
                raise ValidationError("The number of loyalty_points to be awarded can't be negative.")
    
    def _check_loyalty_discount(self):
        for order in self.order:
            if order.loyalty_discount < 0:
                raise ValidationError("The loyalty_discount can't be negative.")