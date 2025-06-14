from odoo import Command
from odoo.tools import float_is_zero
from itertools import groupby

from .constants import AccountMoveLineDisplayType, AccountMoveState, AccountType, SaleOrderState, InvoiceStatus, PaymentTransactionState, OrderLineDisplayType

class SaleOrderInvoicing:
    def __init__(self, order):
        self.order = order
        self.env = order.env
    
    def compute_invoice_status(self, line_invoice_status, lines_domain):
        order = self.order
        if order.state != SaleOrderState.SALE:
            return str(InvoiceStatus.NO)
        elif any(invoice_status == InvoiceStatus.TO_INVOICE for invoice_status in line_invoice_status):
            if any(invoice_status == InvoiceStatus.NO for invoice_status in line_invoice_status):
                # If only discount/delivery/promotion lines can be invoiced, the SO should not
                # be invoiceable.
                invoiceable_domain = lines_domain + [('invoice_status', '=', 'to invoice')]
                invoiceable_lines = order.order_line.filtered_domain(invoiceable_domain)
                special_lines = invoiceable_lines.filtered(
                    lambda sol: not sol._can_be_invoiced_alone()
                )
                if invoiceable_lines == special_lines:
                    return str(InvoiceStatus.NO)
                else:
                    return str(InvoiceStatus.TO_INVOICE)
            else:
                return str(InvoiceStatus.TO_INVOICE)
        elif line_invoice_status and all(invoice_status == InvoiceStatus.INVOICED for invoice_status in line_invoice_status):
            return str(InvoiceStatus.INVOICED)
        elif line_invoice_status and all(invoice_status in (str(InvoiceStatus.INVOICED), str(InvoiceStatus.UPSELLING)) for invoice_status in line_invoice_status):
            return str(InvoiceStatus.UPSELLING)
        else:
            return str(InvoiceStatus.NO)
    
    def create_invoices(self, final, invoice_item_sequence):
        order = self.order

        if order.partner_invoice_id.lang:
            order = order.with_context(lang=order.partner_invoice_id.lang)
        order = order.with_company(order.company_id)

        invoice_vals = order._prepare_invoice()
        invoiceable_lines = order._get_invoiceable_lines(final)

        if not any(not line.display_type for line in invoiceable_lines):
            return None, invoice_item_sequence

        invoice_line_vals = []
        down_payment_section_added = False
        for line in invoiceable_lines:
            if not down_payment_section_added and line.is_downpayment:
                invoice_line_vals.append(
                    Command.create(
                        order._prepare_down_payment_section_line(sequence=invoice_item_sequence)
                    )
                )
                down_payment_section_added = True
                invoice_item_sequence += 1
            invoice_line_vals.append(
                Command.create(
                    line._prepare_invoice_line(sequence=invoice_item_sequence)
                )
            )
            invoice_item_sequence += 1

        invoice_vals['invoice_line_ids'] += invoice_line_vals
        return invoice_vals, invoice_item_sequence
    
    def _get_invoice_grouping_keys(self):
        return ['company_id', 'partner_id', 'currency_id']
    
    def _group_invoice_vals(self, invoice_vals_list):
        new_invoice_vals_list = []
        invoice_grouping_keys = self._get_invoice_grouping_keys()
        invoice_vals_list = sorted(
            invoice_vals_list,
            key=lambda x: [x.get(grouping_key) for grouping_key in invoice_grouping_keys]
        )
        for _grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: [x.get(grouping_key) for grouping_key in invoice_grouping_keys]):
            origins = set()
            payment_refs = set()
            refs = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
                payment_refs.add(invoice_vals['payment_reference'])
                refs.add(invoice_vals['ref'])
            ref_invoice_vals.update({
                'ref': ', '.join(refs)[:2000],
                'invoice_origin': ', '.join(origins),
                'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        return new_invoice_vals_list
    
    def _adjust_downpayment_delta(self, moves, final):
        for move in moves:
            if final:
                # Downpayment might have been determined by a fixed amount set by the user.
                # This amount is tax included. This can lead to rounding issues.
                # E.g. a user wants a 100€ DP on a product with 21% tax.
                # 100 / 1.21 = 82.64, 82.64 * 1,21 = 99.99
                # This is already corrected by adding/removing the missing cents on the DP invoice,
                # but must also be accounted for on the final invoice.

                delta_amount = 0
                for order_line in self.order.order_line:
                    if not order_line.is_downpayment:
                        continue
                    inv_amt = order_amt = 0
                    for invoice_line in order_line.invoice_lines:
                        sign = 1 if invoice_line.move_id.is_inbound() else -1
                        if invoice_line.move_id == move:
                            inv_amt += invoice_line.price_total * sign
                        elif invoice_line.move_id.state != AccountMoveState.CANCEL:  # filter out canceled dp lines
                            order_amt += invoice_line.price_total * sign
                    if inv_amt and order_amt:
                        # if not inv_amt, this order line is not related to current move
                        # if no order_amt, dp order line was not invoiced
                        delta_amount += inv_amt + order_amt

                if not move.currency_id.is_zero(delta_amount):
                    receivable_line = move.line_ids.filtered(
                        lambda aml: aml.account_id.account_type == AccountType.ASSET_RECEIVABLE)[:1]
                    product_lines = move.line_ids.filtered(
                        lambda aml: aml.display_type == AccountMoveLineDisplayType.PRODUCT and aml.is_downpayment)
                    tax_lines = move.line_ids.filtered(
                        lambda aml: aml.tax_line_id.amount_type not in (False, 'fixed'))
                    if tax_lines and product_lines and receivable_line:
                        line_commands = [Command.update(receivable_line.id, {
                            'amount_currency': receivable_line.amount_currency + delta_amount,
                        })]
                        delta_sign = 1 if delta_amount > 0 else -1
                        for lines, attr, sign in (
                            (product_lines, 'price_total', -1 if move.is_inbound() else 1),
                            (tax_lines, 'amount_currency', 1),
                        ):
                            remaining = delta_amount
                            lines_len = len(lines)
                            for line in lines:
                                if move.currency_id.compare_amounts(remaining, 0) != delta_sign:
                                    break
                                amt = delta_sign * max(
                                    move.currency_id.rounding,
                                    abs(move.currency_id.round(remaining / lines_len)),
                                )
                                remaining -= amt
                                line_commands.append(Command.update(line.id, {attr: line[attr] + amt * sign}))
                        move.line_ids = line_commands

            move.message_post_with_source(
                'mail.message_origin_link',
                render_values={'self': move, 'origin': move.line_ids.sale_line_ids.order_id},
                subtype_xmlid='mail.mt_note',
            )
        return moves
    
    def _create_account_invoices(self, invoice_vals_list, final):
        """Small method to allow overriding the behavior right after an invoice is created."""
        # Manage the creation of invoices in sudo because a salesperson must be able to generate an invoice from a
        # sale order without "billing" access rights. However, he should not be able to create an invoice from scratch.
        return self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals_list)
    
    def _get_invoiceable_lines(self, final=False):
        down_payment_line_ids = []
        invoiceable_line_ids = []
        pending_section = None
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for line in self.order.order_line:
            if line.display_type == OrderLineDisplayType.LINE_SECTION:
                # Only invoice the section if one of its lines is invoiceable
                pending_section = line
                continue
            if line.display_type != OrderLineDisplayType.LINE_NOTE and float_is_zero(line.qty_to_invoice, precision_digits=precision):
                continue
            if line.qty_to_invoice > 0 or (line.qty_to_invoice < 0 and final) or line.display_type == OrderLineDisplayType.LINE_NOTE:
                if line.is_downpayment:
                    # Keep down payment lines separately, to put them together
                    # at the end of the invoice, in a specific dedicated section.
                    down_payment_line_ids.append(line.id)
                    continue
                if pending_section:
                    invoiceable_line_ids.append(pending_section.id)
                    pending_section = None
                invoiceable_line_ids.append(line.id)

        return self.env['sale.order.line'].browse(invoiceable_line_ids + down_payment_line_ids)

    @staticmethod
    def _nothing_to_invoice_error_message():
        return _(
            "Cannot create an invoice. No items are available to invoice.\n\n"
            "To resolve this issue, please ensure that:\n"
            "   \u2022 The products have been delivered before attempting to invoice them.\n"
            "   \u2022 The invoicing policy of the product is configured correctly.\n\n"
            "If you want to invoice based on ordered quantities instead:\n"
            "   \u2022 For consumable or storable products, open the product, go to the 'General Information' tab and change the 'Invoicing Policy' from 'Delivered Quantities' to 'Ordered Quantities'.\n"
            "   \u2022 For services (and other products), change the 'Invoicing Policy' to 'Prepaid/Fixed Price'.\n"
        )
    
    def prepare_invoice_dict(self):
        """
        Prepare the dict of values to create a new invoice for the order.
        Exact copy of sale.order._prepare_invoice, adapted to self.order.
        """
        order = self.order
        order.ensure_one()

        txs_to_be_linked = order.transaction_ids.sudo().filtered(
            lambda tx: (
                tx.state in ('pending', 'authorized')
                or tx.state == PaymentTransactionState.DONE and not (tx.payment_id and tx.payment_id.is_reconciled)
            )
        )

        values = {
            'ref': order.client_order_ref or '',
            'move_type': 'out_invoice',
            'narration': order.note,
            'currency_id': order.currency_id.id,
            'campaign_id': order.campaign_id.id,
            'medium_id': order.medium_id.id,
            'source_id': order.source_id.id,
            'team_id': order.team_id.id,
            'partner_id': order.partner_invoice_id.id,
            'partner_shipping_id': order.partner_shipping_id.id,
            'fiscal_position_id': (
                order.fiscal_position_id
                or order.fiscal_position_id._get_fiscal_position(order.partner_invoice_id)
            ).id,
            'invoice_origin': order.name,
            'invoice_payment_term_id': order.payment_term_id.id,
            'invoice_user_id': order.user_id.id,
            'payment_reference': order.reference,
            'transaction_ids': [Command.set(txs_to_be_linked.ids)],
            'company_id': order.company_id.id,
            'invoice_line_ids': [],
            'user_id': order.user_id.id,
        }

        if order.journal_id:
            values['journal_id'] = order.journal_id.id

        return values