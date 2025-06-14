import logging

_logger = logging.getLogger(__name__)
LOYALTY_LOGGING = False

class SaleOrderLoyalty:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def _apply_discount(self, totals):
        if self.order.loyalty_discount <= 0: # should never be smaller than zero though
                return

        percentage = 0
        if totals['amount_untaxed'] > 0:
            percentage = self.order.loyalty_discount/totals['amount_untaxed']

        discounted_untaxed = totals['amount_untaxed'] * (1 - percentage)
        discount_tax = totals['amount_tax'] * (1 - percentage)

        self.order.amount_untaxed = discounted_untaxed
        self.order.amount_tax = discount_tax
        self.order.amount_total = discounted_untaxed + discount_tax

        if not LOYALTY_LOGGING:
            return
        
        _logger.info(f"\n================================================================\n"
                        f"Loyalty discount: {self.order.loyalty_discount} applied\n"
                        f"Untaxed: {totals['amount_untaxed']} -> {self.order.amount_untaxed}\n"
                        f"Tax: {totals['amount_tax']} -> {self.order.amount_tax}\n"
                        f"Total: {totals['amount_total']} -> {self.order.amount_total}\n"
                        f"================================================================\n"
                        )

    def _loyalty_discount(self):
        for order in self.order:
            order.loyalty_discount = 0.0
            if order.amount_untaxed == 0:
                self._loyalty_points()
                continue

            card = self._get_card(order)
            if not card:
                if LOYALTY_LOGGING:
                    _logger.warning(f"Missing loyalty card for customer: {order.partner_id.name} for company: {order.company_id.name}")
                continue

            if not card.discount():
                self._loyalty_points()
                if LOYALTY_LOGGING:
                    _logger.info(f"Customer: {order.partner_id.name} has insufficient points ({card.points}) on their loyalty card for company {order.company_id.name}")
                continue

            if card.discount_type == "p":
                order.loyalty_discount = order.amount_untaxed * card.percentage_discount
            elif card.discount_type == "c":
                order.loyalty_discount = card.currency_discount
            else:
                _logger.error(f"An unsupported loyalty discount {card.discount_type} was used.")

            if card.maxDiscount(order.loyalty_discount):
                order.loyalty_discount = card.max_discount_amount

            order.loyalty_points_used = card.threshold
            # ensure discount never larger than actual price.
            self._loyalty_points()

    def _loyalty_points(self):
        for order in self.order:
            card = self._get_card(order)
            if not card:
                continue

            price = order.amount_untaxed - order.loyalty_discount
            order.loyalty_points = price * card.conversion_rate
            if LOYALTY_LOGGING:
                _logger.info(f"Customer: {order.partner_id.name} stands to gain {order.loyalty_points} points on their loyalty card for company {order.company_id.name}")

    def _get_card(self, order):
        card = self.env['sale.loyalty.card'].search([
            ('partner_id', '=', order.partner_id.id),
            ('company_id', '=', order.company_id.id)
        ], limit=1)
        return card