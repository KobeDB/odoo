from collections import defaultdict
from .constants import AttachedOnSale, SaleOrderState
from odoo import _
from odoo.http import request

class SaleOrderBusiness:
    def __init__(self, order):
        self.order = order
        self.env = order.env
    
    def _create_upsell_activity(self):
        if not self.order:
            return

        self.order.activity_unlink(['sale.mail_act_sale_upsell'])
        for order in self.order:
            order_ref = order._get_html_link()
            customer_ref = order.partner_id._get_html_link()
            order.activity_schedule(
                'sale.mail_act_sale_upsell',
                user_id=order.user_id.id or order.partner_id.user_id.id,
                note=_("Upsell %(order)s for customer %(customer)s", order=order_ref, customer=customer_ref))
    
    def _prepare_analytic_account_data(self, prefix=None):
        """ Prepare SO analytic account creation values.

        :return: `account.analytic.account` creation values
        :rtype: dict
        """
        self.order.ensure_one()
        name = self.order.name
        if prefix:
            name = prefix + ": " + self.order.name
        project_plan, _other_plans = self.order.env['account.analytic.plan']._get_all_plans()
        return {
            'name': name,
            'code': self.order.client_order_ref,
            'company_id': self.order.company_id.id,
            'plan_id': project_plan.order.id,
            'partner_id': self.partner_id.order.id,
        }
    
    def _prepare_down_payment_section_line(self, **optional_values):
        """ Prepare the values to create a new down payment section.

        :param dict optional_values: any parameter that should be added to the returned down payment section
        :return: `account.move.line` creation values
        :rtype: dict
        """
        self.order.ensure_one()
        context = {'lang': self.order.partner_id.lang}
        down_payments_section_line = {
            'display_type': 'line_section',
            'name': _("Down Payments"),
            'product_id': False,
            'product_uom_id': False,
            'quantity': 0,
            'discount': 0,
            'price_unit': 0,
            'account_id': False,
            **optional_values
        }
        del context
        return down_payments_section_line
    
    def _get_prepayment_required_amount(self):
        """ Return the minimum amount needed to confirm automatically the quotation.

        Note: self.ensure_one()

        :return: The minimum amount needed to confirm automatically the quotation.
        :rtype: float
        """
        self.order.ensure_one()
        if self.order.prepayment_percent == 1.0 or not self.order.require_payment:
            return self.order.amount_total
        else:
            return self.order.currency_id.round(self.order.amount_total * self.order.prepayment_percent)
    
    def _is_confirmation_amount_reached(self):
        """ Return whether `self.amount_paid` is higher than the prepayment required amount.

        Note: self.ensure_one()

        :return: Whether `self.amount_paid` is higher than the prepayment required amount.
        :rtype: bool
        """
        self.order.ensure_one()
        amount_comparison = self.order.currency_id.compare_amounts(
            self._get_prepayment_required_amount(), self.order.amount_paid,
        )
        return amount_comparison <= 0
    
    def _generate_downpayment_invoices(self):
        """ Generate invoices as down payments for sale order.

        :return: The generated down payment invoices.
        :rtype: recordset of `account.move`
        """
        generated_invoices = self.order.env['account.move']

        for order in self.order:
            downpayment_wizard = order.env['sale.advance.payment.inv'].create({
                'sale_order_ids': order,
                'advance_payment_method': 'fixed',
                'fixed_amount': order.amount_paid,
            })
            generated_invoices |= downpayment_wizard._create_invoices(order)

        return generated_invoices
    
    def _get_product_catalog_order_data(self, products, res, **kwargs):
        pricelist = self.order.pricelist_id._get_products_price(
            quantity=1.0,
            products=products,
            currency=self.order.currency_id,
            date=self.order.date_order,
            **kwargs,
        )
        for product in products:
            res[product.id]['price'] = pricelist.get(product.id)
            if product.sale_line_warn != 'no-message' and product.sale_line_warn_msg:
                res[product.id]['warning'] = product.sale_line_warn_msg
            if product.sale_line_warn == "block":
                res[product.id]['readOnly'] = True
        return res
    
    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        grouped_lines = defaultdict(lambda: self.env['sale.order.line'])
        for line in self.order.order_line:
            if line.display_type or line.product_id.id not in product_ids:
                continue
            grouped_lines[line.product_id] |= line
        return grouped_lines

    def _get_product_documents(self):
        self.order.ensure_one()

        documents = (
            self.order.order_line.product_id.product_document_ids
            | self.order.order_line.product_template_id.product_document_ids
        )
        return self._filter_product_documents(documents).sorted()
    
    def _filter_product_documents(self, documents):
        return documents.filtered(
            lambda document:
                document.attached_on_sale == AttachedOnSale.QUOTATION
                or (self.order.state == SaleOrderState.SALE and document.attached_on_sale == AttachedOnSale.SALE_ORDER)
        )
    
    def _update_order_line_info(self, product_id, quantity, **kwargs):
        """ Update sale order line information for a given product or create a
        new one if none exists yet.
        :param int product_id: The product, as a `product.product` id.
        :return: The unit price of the product, based on the pricelist of the
                 sale order and the quantity selected.
        :rtype: float
        """
        request.update_context(catalog_skip_tracking=True)
        sol = self.order.order_line.filtered(lambda line: line.product_id.id == product_id)
        if sol:
            if quantity != 0:
                sol.product_uom_qty = quantity
            elif self.order.state in ['draft', 'sent']:
                price_unit = self.order.pricelist_id._get_product_price(
                    product=sol.product_id,
                    quantity=1.0,
                    currency=self.order.currency_id,
                    date=self.order.date_order,
                    **kwargs,
                )
                sol.unlink()
                return price_unit
            else:
                sol.product_uom_qty = 0
        elif quantity > 0:
            sol = self.env['sale.order.line'].create({
                'order_id': self.order.id,
                'product_id': product_id,
                'product_uom_qty': quantity,
                'sequence': ((self.order.order_line and self.order.order_line[-1].sequence + 1) or 10),  # put it at the end of the order
            })
        return sol.price_unit * (1-(sol.discount or 0.0)/100.0)