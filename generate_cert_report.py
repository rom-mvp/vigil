#!/usr/bin/env python3
"""
Vigil Security Certification Report Generator
Generates comprehensive PDF/HTML security assessment reports
"""
import json
import sys
from datetime import datetime
from pathlib import Path

def generate_html_report(test_results_file):
    """Generate comprehensive HTML security report"""
    
    # Load test results
    with open(test_results_file, 'r') as f:
        data = json.load(f)
    
    timestamp = data.get('timestamp', datetime.now().isoformat())
    total_tests = data.get('total_tests', 0)
    passed = data.get('passed', 0)
    failed = data.get('failed', 0)
    pass_rate = data.get('pass_rate', 0)
    category_results = data.get('category_results', {})
    detailed_results = data.get('detailed_results', [])
    
    # Calculate threat statistics
    threat_types = {}
    blocked_attacks = 0
    allowed_benign = 0
    false_positives = 0
    false_negatives = 0
    
    for result in detailed_results:
        tt = result.get('threat_type', 'none')
        threat_types[tt] = threat_types.get(tt, 0) + 1
        
        if result.get('expected_block') and result.get('actual_block'):
            blocked_attacks += 1
        elif not result.get('expected_block') and not result.get('actual_block'):
            allowed_benign += 1
        elif not result.get('expected_block') and result.get('actual_block'):
            false_positives += 1
        elif result.get('expected_block') and not result.get('actual_block'):
            false_negatives += 1
    
    # Security rating
    if pass_rate >= 95:
        rating = "EXCELLENT"
        rating_color = "#10b981"
        rating_icon = "🟢"
    elif pass_rate >= 85:
        rating = "GOOD"
        rating_color = "#3b82f6"
        rating_icon = "🔵"
    elif pass_rate >= 70:
        rating = "FAIR"
        rating_color = "#f59e0b"
        rating_icon = "🟡"
    else:
        rating = "POOR"
        rating_color = "#ef4444"
        rating_icon = "🔴"
    
    # Production readiness
    prod_ready = pass_rate >= 90 and false_negatives == 0
    prod_status = "READY FOR PRODUCTION" if prod_ready else "REQUIRES IMPROVEMENTS"
    prod_color = "#10b981" if prod_ready else "#ef4444"
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vigil Security Certification Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            background: #f9fafb;
            padding: 40px 20px;
        }}
        
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            border-radius: 12px;
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 50px 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 36px;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            font-size: 18px;
            opacity: 0.9;
        }}
        
        .header .date {{
            margin-top: 20px;
            font-size: 14px;
            opacity: 0.8;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            font-size: 24px;
            color: #111827;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        
        .rating-card {{
            background: linear-gradient(135deg, {rating_color}, {rating_color});
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .rating-card .icon {{
            font-size: 48px;
            margin-bottom: 15px;
        }}
        
        .rating-card .rating {{
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        
        .rating-card .score {{
            font-size: 20px;
            opacity: 0.9;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}
        
        .stat-card .value {{
            font-size: 36px;
            font-weight: bold;
            color: #111827;
            margin-bottom: 5px;
        }}
        
        .stat-card .label {{
            font-size: 14px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .stat-card.success {{
            border-color: #10b981;
            background: #ecfdf5;
        }}
        
        .stat-card.success .value {{
            color: #10b981;
        }}
        
        .stat-card.danger {{
            border-color: #ef4444;
            background: #fef2f2;
        }}
        
        .stat-card.danger .value {{
            color: #ef4444;
        }}
        
        .category-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
        }}
        
        .category-table th {{
            background: #f3f4f6;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #e5e7eb;
        }}
        
        .category-table td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        .category-table tr:hover {{
            background: #f9fafb;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        
        .badge.pass {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .badge.fail {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .progress-bar {{
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        
        .progress-bar-fill {{
            height: 100%;
            background: #10b981;
            transition: width 0.3s ease;
        }}
        
        .production-status {{
            background: {prod_color};
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            font-size: 20px;
            font-weight: bold;
            margin-top: 30px;
        }}
        
        .threat-breakdown {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 20px;
        }}
        
        .threat-item {{
            flex: 1;
            min-width: 150px;
            background: #f9fafb;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .threat-item .count {{
            font-size: 24px;
            font-weight: bold;
            color: #111827;
        }}
        
        .threat-item .label {{
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
        }}
        
        .recommendations {{
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 20px;
            border-radius: 4px;
            margin-top: 20px;
        }}
        
        .recommendations h3 {{
            color: #92400e;
            margin-bottom: 10px;
        }}
        
        .recommendations ul {{
            margin-left: 20px;
            color: #78350f;
        }}
        
        .recommendations li {{
            margin-bottom: 8px;
        }}
        
        .footer {{
            background: #f3f4f6;
            padding: 30px 40px;
            text-align: center;
            color: #6b7280;
            font-size: 14px;
        }}
        
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Vigil Security Certification Report</h1>
            <p class="subtitle">Comprehensive LLM Security Assessment</p>
            <p class="date">Generated: {datetime.now().strftime("%B %d, %Y at %H:%M:%S")}</p>
        </div>
        
        <div class="content">
            <!-- Overall Rating -->
            <div class="section">
                <h2>Security Rating</h2>
                <div class="rating-card">
                    <div class="icon">{rating_icon}</div>
                    <div class="rating">{rating}</div>
                    <div class="score">Pass Rate: {pass_rate:.1f}%</div>
                </div>
            </div>
            
            <!-- Key Statistics -->
            <div class="section">
                <h2>Test Summary</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="value">{total_tests}</div>
                        <div class="label">Total Tests</div>
                    </div>
                    <div class="stat-card success">
                        <div class="value">{passed}</div>
                        <div class="label">Passed</div>
                    </div>
                    <div class="stat-card danger">
                        <div class="value">{failed}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="stat-card">
                        <div class="value">{pass_rate:.1f}%</div>
                        <div class="label">Success Rate</div>
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card success">
                        <div class="value">{blocked_attacks}</div>
                        <div class="label">Attacks Blocked</div>
                    </div>
                    <div class="stat-card success">
                        <div class="value">{allowed_benign}</div>
                        <div class="label">Benign Allowed</div>
                    </div>
                    <div class="stat-card danger">
                        <div class="value">{false_negatives}</div>
                        <div class="label">False Negatives</div>
                    </div>
                    <div class="stat-card">
                        <div class="value">{false_positives}</div>
                        <div class="label">False Positives</div>
                    </div>
                </div>
            </div>
            
            <!-- Category Breakdown -->
            <div class="section">
                <h2>Category Performance</h2>
                <table class="category-table">
                    <thead>
                        <tr>
                            <th>Attack Category</th>
                            <th>Tests</th>
                            <th>Passed</th>
                            <th>Failed</th>
                            <th>Success Rate</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
"""
    
    for category, results in category_results.items():
        success_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
        status = "pass" if results['failed'] == 0 else "fail"
        html += f"""
                        <tr>
                            <td><strong>{category}</strong></td>
                            <td>{results['total']}</td>
                            <td style="color: #10b981;">{results['passed']}</td>
                            <td style="color: #ef4444;">{results['failed']}</td>
                            <td>
                                {success_rate:.0f}%
                                <div class="progress-bar">
                                    <div class="progress-bar-fill" style="width: {success_rate}%"></div>
                                </div>
                            </td>
                            <td><span class="badge {status}">{'PASS' if status == 'pass' else 'FAIL'}</span></td>
                        </tr>
"""
    
    html += """
                    </tbody>
                </table>
            </div>
            
            <!-- Threat Type Breakdown -->
            <div class="section">
                <h2>Threat Detection Analysis</h2>
                <div class="threat-breakdown">
"""
    
    for threat_type, count in threat_types.items():
        if threat_type and threat_type != 'none':
            html += f"""
                    <div class="threat-item">
                        <div class="count">{count}</div>
                        <div class="label">{threat_type.replace('_', ' ').title()}</div>
                    </div>
"""
    
    html += """
                </div>
            </div>
            
            <!-- Recommendations -->
            <div class="section">
                <h2>Recommendations</h2>
"""
    
    if false_negatives > 0:
        html += f"""
                <div class="recommendations">
                    <h3>⚠️ Critical Issues Detected</h3>
                    <ul>
                        <li><strong>{false_negatives} attacks were not blocked</strong> - Review detection patterns immediately</li>
                        <li>Update threat signatures for missed attack vectors</li>
                        <li>Consider lowering risk score threshold from 0.70 to 0.65</li>
                        <li>Do NOT deploy to production until all attacks are blocked</li>
                    </ul>
                </div>
"""
    elif false_positives > 0:
        html += f"""
                <div class="recommendations">
                    <h3>⚠️ False Positives Detected</h3>
                    <ul>
                        <li><strong>{false_positives} benign requests were incorrectly blocked</strong></li>
                        <li>Review and refine detection patterns to reduce false positives</li>
                        <li>Consider raising risk score threshold from 0.70 to 0.75</li>
                        <li>Safe to deploy but may impact user experience</li>
                    </ul>
                </div>
"""
    else:
        html += """
                <div class="recommendations" style="background: #d1fae5; border-left-color: #10b981;">
                    <h3 style="color: #065f46;">✅ Excellent Security Posture</h3>
                    <ul style="color: #064e3b;">
                        <li>All attacks successfully blocked with zero false negatives</li>
                        <li>No false positives - benign requests handled correctly</li>
                        <li>Security features are production-ready</li>
                        <li>Recommended: Deploy with confidence and monitor in production</li>
                        <li>Continue updating threat patterns as new attack vectors emerge</li>
                    </ul>
                </div>
"""
    
    html += f"""
            </div>
            
            <!-- Production Status -->
            <div class="production-status">
                {prod_status}
            </div>
            
            <!-- Detailed Results -->
            <div class="section" style="margin-top: 40px;">
                <h2>Detailed Test Results</h2>
                <table class="category-table">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Test Name</th>
                            <th>Expected</th>
                            <th>Actual</th>
                            <th>Risk Score</th>
                            <th>Result</th>
                        </tr>
                    </thead>
                    <tbody>
"""
    
    for result in detailed_results:
        expected = "BLOCK" if result.get('expected_block') else "ALLOW"
        actual = "BLOCK" if result.get('actual_block') else "ALLOW"
        risk_score = result.get('risk_score', 0) * 100
        status = "pass" if result.get('passed') else "fail"
        
        html += f"""
                        <tr>
                            <td>{result.get('category', 'Unknown')[:30]}</td>
                            <td>{result.get('test_name', 'Unknown')}</td>
                            <td>{expected}</td>
                            <td>{actual}</td>
                            <td>{risk_score:.0f}%</td>
                            <td><span class="badge {status}">{'PASS' if status == 'pass' else 'FAIL'}</span></td>
                        </tr>
"""
    
    html += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>Vigil Security Assessment Report</strong></p>
            <p>This report certifies that the Vigil LLM security gateway has been tested against comprehensive attack vectors.</p>
            <p style="margin-top: 10px;">For questions or support, contact: security@vigil.ai</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 generate_cert_report.py <test_results.json>")
        sys.exit(1)
    
    test_file = sys.argv[1]
    
    if not Path(test_file).exists():
        print(f"Error: File not found: {test_file}")
        sys.exit(1)
    
    print("Generating security certification report...")
    html_report = generate_html_report(test_file)
    
    output_file = test_file.replace('.json', '_certification.html')
    with open(output_file, 'w') as f:
        f.write(html_report)
    
    print(f"✅ Report generated: {output_file}")
    print(f"📄 Open in browser: file://{Path(output_file).absolute()}")
