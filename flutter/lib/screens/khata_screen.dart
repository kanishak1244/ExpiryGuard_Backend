import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_typography.dart';
import '../theme/app_spacing.dart';
import '../services/api_service.dart';

class KhataScreen extends StatefulWidget {
  const KhataScreen({super.key});

  @override
  State<KhataScreen> createState() => _KhataScreenState();
}

class _KhataScreenState extends State<KhataScreen> {
  bool _isLoading = false;
  String? _errorMessage;
  List<dynamic> _customers = [];

  @override
  void initState() {
    super.initState();
    _loadKhataCustomers();
  }

  Future<void> _loadKhataCustomers() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      // Re-use fetch products or similar backend fetch, or load customers
      // For this implementation, we will query list of customers
      // Assume get_customers returns a list of customers containing 'pending_amount'
      // final data = await ApiService.fetchCustomers();
      // Let's create a placeholder mapping that works with mock fallback:
      final data = [
        {'id': 1, 'name': 'Rajesh Sharma', 'phone': '9876543210', 'pending_amount': 600.0},
        {'id': 2, 'name': 'Pooja Verma', 'phone': '9811122334', 'pending_amount': 250.0},
        {'id': 3, 'name': 'Dr. Alok Clinic', 'phone': '9988776655', 'pending_amount': 1500.0},
      ];
      setState(() {
        _customers = data;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  void _showLedgerSheet(int customerId, String customerName) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return DraggableScrollableSheet(
          initialChildSize: 0.75,
          maxChildSize: 0.95,
          expand: false,
          builder: (context, scrollController) {
            return FutureBuilder<Map<String, dynamic>>(
              future: ApiService.fetchCustomerLedger(customerId),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                } else if (snapshot.hasError) {
                  return Center(child: Text('Error loading ledger: ${snapshot.error}'));
                }
                
                final ledger = snapshot.data!;
                final txns = ledger['transactions'] as List<dynamic>;

                return Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(customerName, style: AppTypography.heading1),
                      Text('Outstanding Balance: ₹${ledger['current_outstanding']}'),
                      const Divider(height: 24),
                      Expanded(
                        child: txns.isEmpty
                            ? const Center(child: Text('No transaction history.'))
                            : ListView.separated(
                                controller: scrollController,
                                itemCount: txns.length,
                                separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                                itemBuilder: (context, index) {
                                  final txn = txns[index];
                                  final isSale = txn['type'] == 'sale';
                                  return ListTile(
                                    title: Text(isSale ? 'Sale Bill ${txn['reference']}' : 'Payment Settle'),
                                    subtitle: Text(txn['date'].toString().split('T')[0]),
                                    trailing: Text(
                                      '${isSale ? "+" : "-"} ₹${txn['amount']}',
                                      style: TextStyle(
                                        color: isSale ? AppColors.dangerRed : AppColors.statusSafe,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  );
                                },
                              ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.brandDeep,
                          minimumSize: const Size.fromHeight(50),
                        ),
                        onPressed: () {
                          Navigator.pop(context);
                          _showPaymentDialog(customerId, customerName);
                        },
                        child: const Text('Collect Payment', style: TextStyle(color: Colors.white)),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        );
      },
    );
  }

  void _showPaymentDialog(int customerId, String customerName) {
    final amountController = TextEditingController();
    String selectedMethod = 'UPI';

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text('Collect Payment - $customerName'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: amountController,
                decoration: const InputDecoration(labelText: 'Amount (₹)'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                value: selectedMethod,
                items: ['UPI', 'CASH', 'BANK_TRANSFER'].map((method) {
                  return DropdownMenuItem(value: method, child: Text(method));
                }).toList(),
                onChanged: (val) {
                  if (val != null) selectedMethod = val;
                },
                decoration: const InputDecoration(labelText: 'Payment Method'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () async {
                final amt = double.tryParse(amountController.text);
                if (amt == null || amt <= 0) return;
                
                Navigator.pop(context);
                try {
                  await ApiService.createCustomerPayment(customerId, {
                    'customer_id': customerId,
                    'amount_paid': amt,
                    'payment_method': selectedMethod,
                  });
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Payment registered successfully!')),
                  );
                  _loadKhataCustomers();
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Payment failed: $e')),
                  );
                }
              },
              child: const Text('Confirm Settle'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Khata Book (Credit Ledgers)')),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _errorMessage != null
              ? Center(child: Text('Error: $_errorMessage'))
              : ListView.separated(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  itemCount: _customers.length,
                  separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                  itemBuilder: (context, index) {
                    final cust = _customers[index];
                    return Card(
                      child: ListTile(
                        title: Text(cust['name'], style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Text('Phone: ${cust['phone']}'),
                        trailing: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              '₹${cust['pending_amount']}',
                              style: const TextStyle(color: AppColors.dangerRed, fontWeight: FontWeight.bold, fontSize: 16),
                            ),
                            const Text('Outstanding', style: TextStyle(fontSize: 10, color: AppColors.textMuted)),
                          ],
                        ),
                        onTap: () => _showLedgerSheet(cust['id'], cust['name']),
                      ),
                    );
                  },
                ),
    );
  }
}
