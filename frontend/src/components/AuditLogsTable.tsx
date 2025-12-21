import { useEffect, useState } from "react";
import { fetchAuditLogs } from "../api/client";
import type { AuditLog } from "../types";

export default function AuditLogsTable() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadLogs = async () => {
      try {
        setLoading(true);
        const response = await fetchAuditLogs();
        setLogs(response.data.logs || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load audit logs");
      } finally {
        setLoading(false);
      }
    };

    loadLogs();
    const interval = setInterval(loadLogs, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  if (loading && logs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-800 flex justify-between items-center">
        <h2 className="text-lg font-semibold">Audit Logs</h2>
        <span className="text-xs text-slate-400">{logs.length} entries</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
            <tr>
              <th className="px-4 py-3 text-left">Timestamp</th>
              <th className="px-4 py-3 text-left">Agent ID</th>
              <th className="px-4 py-3 text-left">Tenant</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Endpoint</th>
              <th className="px-4 py-3 text-left">Signature Hash</th>
              <th className="px-4 py-3 text-left">Audit Event</th>
              <th className="px-4 py-3 text-left">Risk</th>
              <th className="px-4 py-3 text-left">Reasons</th>
              <th className="px-4 py-3 text-left">Verdict</th>
              <th className="px-4 py-3 text-left">SBOM</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {logs.map((log) => (
              <tr
                key={log.id}
                className="hover:bg-slate-800/30 transition-colors"
              >
                <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                  {new Date(log.timestamp).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  <span className="font-mono text-xs text-slate-400">
                    {log.agent_id}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">
                  {log.tenant_id || "-"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                      log.status === "BLOCKED"
                        ? "bg-red-500/20 text-red-400"
                        : log.status === "MODIFIED"
                        ? "bg-yellow-500/20 text-yellow-400"
                        : "bg-green-500/20 text-green-400"
                    }`}
                  >
                    {log.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">
                  {log.endpoint}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="font-mono text-xs text-indigo-400 hover:text-indigo-300 cursor-pointer"
                    title={log.signature_hash}
                  >
                    {log.signature_hash.substring(0, 12)}...
                  </span>
                </td>
                <td className="px-4 py-3">
                  {log.audit_event_id ? (
                    <span className="font-mono text-xs text-slate-400" title={log.audit_event_id}>
                      {log.audit_event_id.substring(0, 10)}...
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {typeof log.risk_score === "number" ? (
                    <span className={`text-xs ${
                      log.risk_score >= 0.8 ? "text-red-400" : log.risk_score >= 0.4 ? "text-yellow-400" : "text-green-400"
                    }`}>
                      {Math.round(log.risk_score * 100)}%
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {log.reasons && log.reasons.length > 0 ? (
                    <span className="text-xs text-slate-400" title={log.reasons.join("\n")}>
                      {log.reasons.slice(0, 2).join(", ")}{log.reasons.length > 2 ? "…" : ""}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {log.classifier_verdict && (
                    <span
                      className={`text-xs ${
                        log.classifier_verdict === "MALICIOUS"
                          ? "text-red-400"
                          : log.classifier_verdict === "SUSPICIOUS"
                          ? "text-yellow-400"
                          : "text-green-400"
                      }`}
                    >
                      {log.classifier_verdict}
                    </span>
                  )}
                  {log.scanner_verdict && (
                    <span className="text-xs text-slate-500 ml-1">
                      / {log.scanner_verdict}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {log.sbom_verified !== undefined && (
                    <span
                      className={`text-xs ${
                        log.sbom_verified ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {log.sbom_verified ? "✓ Verified" : "✗ Failed"}
                    </span>
                  )}
                  {log.poisoning_detected && (
                    <span className="ml-2 text-xs text-red-400">
                      🚨 Poisoning
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {logs.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          No audit logs found
        </div>
      )}
    </div>
  );
}
