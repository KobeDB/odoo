import logging

_logger = logging.getLogger(__name__)

class SaleOrderLoyalty:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def _loyalty_discount(self):
        for order in self.order:
            order.loyalty_discount = 0.0
            card = self.env['sale.loyalty.card'].search([
                ('partner_id', '=', order.partner_id.id),
                ('company_id', '=', order.company_id.id)
            ], limit=1)
            if not card:
                _logger.warning(f"Missing loyalty card for customer: {order.partner_id.name} for company: {order.company_id.name}")
                _logger.info(f"Created loyalty card for customer: {order.partner_id.name} for company: {order.company_id.name}")
                order.company_id._create_loyalty_cards_for_customer(order.partner_id)
                self._loyalty_points()
                # wont have to apply discount yet since card just created
                return

            if card.points < card.threshold:
                _logger.info(f"Customer: {order.partner_id.name} has insufficient points ({card.points}) on their loyalty card for company {order.company_id.name}")
                self._loyalty_points()
                return

            if card.discount_type == "p":
                order.loyalty_discount = order.amount_untaxed * card.percentage_discount
            elif card.discount_type == "c":
                order.loyalty_discount = card.currency_discount
            else:
                _logger.error(f"An unsupported loyalty discount {card.discount_type} was used.")

            if card.max_discount and card.max_discount_amount < order.loyalty_discount:
                order.loyalty_discount = card.max_discount_amount

            order.loyalty_points_used = card.threshold
            # ensure discount never larger than actual price.
            self._loyalty_points()
        
    def _loyalty_points(self):
        for order in self.order:
            card = self.env['sale.loyalty.card'].search([
                ('partner_id', '=', order.partner_id.id),
                ('company_id', '=', order.company_id.id)
            ], limit=1)

            price = order.amount_untaxed - order.loyalty_discount
            order.loyalty_points = price * card.conversion_rate
            _logger.info(f"Customer: {order.partner_id.name} stands to gain {order.loyalty_points} points on their loyalty card for company {order.company_id.name}")