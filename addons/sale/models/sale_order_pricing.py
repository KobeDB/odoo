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
        pt = self.order.payment_term_id
        if not (
            pt.early_discount and
            pt.early_pay_discount_computation == 'mixed' and
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