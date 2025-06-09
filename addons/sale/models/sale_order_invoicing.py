from odoo import Command
from itertools import groupby

class SaleOrderInvoicing:
    def __init__(self, order):
        self.order = order
        self.env = order.env
    
    def compute_invoice_status(self, line_invoice_status):
        order = self.order
        if order.state != 'sale':
            return 'no'

        if any(invoice_status == 'to invoice' for invoice_status in line_invoice_status):
            if any(invoice_status == 'no' for invoice_status in line_invoice_status):
                invoiceable_domain = [
                    ('is_downpayment', '=', False),
                    ('display_type', '=', False),
                    ('invoice_status', '=', 'to invoice')
                ]
                invoiceable_lines = order.order_line.filtered_domain(invoiceable_domain)
                special_lines = invoiceable_lines.filtered(
                    lambda sol: not sol._can_be_invoiced_alone()
                )
                if invoiceable_lines == special_lines:
                    return 'no'
                else:
                    return 'to invoice'
            else:
                return 'to invoice'

        elif line_invoice_status and all(s == 'invoiced' for s in line_invoice_status):
            return 'invoiced'

        elif line_invoice_status and all(s in ('invoiced', 'upselling') for s in line_invoice_status):
            return 'upselling'

        return 'no'
    
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
                        elif invoice_line.move_id.state != 'cancel':  # filter out canceled dp lines
                            order_amt += invoice_line.price_total * sign
                    if inv_amt and order_amt:
                        # if not inv_amt, this order line is not related to current move
                        # if no order_amt, dp order line was not invoiced
                        delta_amount += inv_amt + order_amt

                if not move.currency_id.is_zero(delta_amount):
                    receivable_line = move.line_ids.filtered(
                        lambda aml: aml.account_id.account_type == 'asset_receivable')[:1]
                    product_lines = move.line_ids.filtered(
                        lambda aml: aml.display_type == 'product' and aml.is_downpayment)
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
                subtype_xmlid='mail.mt_note',)
        return moves
    
    def _create_account_invoices(self, invoice_vals_list, final):
        """Small method to allow overriding the behavior right after an invoice is created."""
        # Manage the creation of invoices in sudo because a salesperson must be able to generate an invoice from a
        # sale order without "billing" access rights. However, he should not be able to create an invoice from scratch.
        return self.env['account.move'].sudo().with_context(default_move_type='out_invoice').create(invoice_vals_list)
