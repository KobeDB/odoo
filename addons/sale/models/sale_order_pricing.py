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
        AccountTax = self.env['account.tax']
        order_lines = self.order.order_line.filtered(lambda x: not x.display_type)

        base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
        base_lines += self.compute_early_payment_discount()

        AccountTax._add_tax_details_in_base_lines(base_lines, self.company)
        AccountTax._round_base_lines_tax_details(base_lines, self.company)

        tax_totals = AccountTax._get_tax_totals_summary(
            base_lines=base_lines,
            currency=self.currency,
            company=self.company,
        )

        return {
            'amount_untaxed': tax_totals['base_amount_currency'],
            'amount_tax': tax_totals['tax_amount_currency'],
            'amount_total': tax_totals['total_amount_currency'],
        }

    def compute_early_payment_discount(self):
        """
        Add tax lines for early payment discounts if applicable.
        Returns a list of base lines.
        """
        self.order.ensure_one()
        epd_lines = []
        if (
            self.order.payment_term_id.early_discount
            and self.order.payment_term_id.early_pay_discount_computation == EarlyPayDiscountComputation.MIXED
            and self.order.payment_term_id.discount_percentage
        ):
            percentage = self.order.payment_term_id.discount_percentage
            currency = self.order.currency_id or self.order.company_id.currency_id
            for line in self.order.order_line.filtered(lambda x: not x.display_type):
                line_amount_after_discount = (line.price_subtotal / 100) * percentage
                epd_lines.append(self.env['account.tax']._prepare_base_line_for_taxes_computation(
                    record=self.order,
                    price_unit=-line_amount_after_discount,
                    quantity=1.0,
                    currency_id=currency,
                    sign=1,
                    special_type='early_payment',
                    tax_ids=line.tax_id,
                ))
                epd_lines.append(self.env['account.tax']._prepare_base_line_for_taxes_computation(
                    record=self.order,
                    price_unit=line_amount_after_discount,
                    quantity=1.0,
                    currency_id=currency,
                    sign=1,
                    special_type='early_payment',
                ))
        return epd_lines

    def compute_tax_totals(self):
        AccountTax = self.env['account.tax']
        order_lines = self.order.order_line.filtered(lambda x: not x.display_type)

        base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
        base_lines += self.compute_early_payment_discount()

        AccountTax._add_tax_details_in_base_lines(base_lines, self.company)
        AccountTax._round_base_lines_tax_details(base_lines, self.company)

        return AccountTax._get_tax_totals_summary(
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
        total = 0.0
        for line in self.order.order_line:
            if line.discount != 100:
                total += (line.price_subtotal * 100.0) / (100.0 - line.discount)
            else:
                total += line.price_unit * line.product_uom_qty
        return total
    
    def get_currency_id(self):
        return self.order.pricelist_id.currency_id or self.order.company_id.currency_id

    def get_currency_rate(self):
        currency = self.order.currency_id
        date = (self.order.date_order or fields.Datetime.now()).date()
        return self.env['res.currency']._get_conversion_rate(
            from_currency=self.order.company_id.currency_id,
            to_currency=currency,
            company=self.order.company_id,
            date=date,
        )