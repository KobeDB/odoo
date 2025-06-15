from odoo import fields
from .constants import EarlyPayDiscountComputation

class SaleOrderPricing:
    def __init__(self, order):
        self.order = order
        self.env = order.env
        self.company = order.company_id
        self.currency = order.currency_id or self.company.currency_id

    def compute_totals(self):
        """
        Compute untaxed, tax, and total amounts for the sale order.
        """
        for order in self.order:
            AccountTax = self.env['account.tax']
            order_lines = order.order_line.filtered(lambda x: not x.display_type)

            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            base_lines += self.compute_early_payment_discount()

            AccountTax._add_tax_details_in_base_lines(base_lines, self.company)
            AccountTax._round_base_lines_tax_details(base_lines, self.company)

            tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=self.currency,
                company=self.company,
            )

            order.amount_untaxed = tax_totals['base_amount_currency']
            order.amount_tax = tax_totals['tax_amount_currency']
            order.amount_total = tax_totals['total_amount_currency']

            totals = {
                'amount_untaxed': tax_totals['base_amount_currency'],
                'amount_tax': tax_totals['tax_amount_currency'],
                'amount_total': tax_totals['total_amount_currency'],
            }

            order.loyalty._loyalty_discount()
            order.loyalty._apply_discount(totals)

    def compute_early_payment_discount(self):
        """
        Add tax lines for early payment discounts if applicable.
        Returns a list of base lines.
        """
        pt = self.order.payment_term_id
        if not (
            pt.early_discount and
            pt.early_pay_discount_computation == EarlyPayDiscountComputation.MIXED and
            pt.discount_percentage
        ):
            return []

        percentage = pt.discount_percentage
        lines = []
        AccountTax = self.env['account.tax']

        for line in self.order.order_line.filtered(lambda x: not x.display_type):
            discount_amount = (line.price_subtotal / 100.0) * percentage
            lines.append(AccountTax._prepare_base_line_for_taxes_computation(
                record=self.order,
                price_unit=-discount_amount,
                quantity=1.0,
                currency_id=self.currency,
                sign=1,
                special_type='early_payment',
                tax_ids=line.tax_id,
            ))
            lines.append(AccountTax._prepare_base_line_for_taxes_computation(
                record=self.order,
                price_unit=discount_amount,
                quantity=1.0,
                currency_id=self.currency,
                sign=1,
                special_type='early_payment',
            ))
        return lines

    def compute_tax_totals(self):
        for order in self.order:
            AccountTax = self.env['account.tax']
            order_lines = order.order_line.filtered(lambda x: not x.display_type)

            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            base_lines += self.compute_early_payment_discount()

            AccountTax._add_tax_details_in_base_lines(base_lines, self.company)
            AccountTax._round_base_lines_tax_details(base_lines, self.company)

            order.tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=self.currency,
                company=self.company,
            )

    def _get_update_prices_lines(self):
        return self.order.order_line.filtered(lambda line: not line.display_type)


    def recompute_prices(self):
        lines = self._get_update_prices_lines()

        lines.invalidate_recordset(['pricelist_item_id'])

        lines.with_context(force_price_recomputation=True)._compute_price_unit()
        lines.discount = 0.0
        lines._compute_discount()

        self.order.show_update_pricelist = False
    
    def recompute_taxes(self):
        lines_to_recompute = self.order.order_line.filtered(lambda line: not line.display_type)
        lines_to_recompute._compute_tax_id()
        self.order.show_update_fpos = False
    
    def compute_amount_undiscounted(self):
        for order in self.order:
            total = 0.0
            for line in order.order_line:
                if line.discount != 100:
                    total += (line.price_subtotal * 100.0) / (100.0 - line.discount)
                else:
                    total += line.price_unit * line.product_uom_qty
            order.amount_undiscounted = total
    
    def compute_currency_id(self):
        for order in self.order:
            order.currency_id = order.pricelist_id.currency_id or order.company_id.currency_id

    def compute_currency_rate(self):
        for order in self.order:
            currency = order.currency_id
            date = (order.date_order or fields.Datetime.now()).date()
            order.currency_rate = self.env['res.currency']._get_conversion_rate(
                from_currency=order.company_id.currency_id,
                to_currency=currency,
                company=order.company_id,
                date=date,
            )