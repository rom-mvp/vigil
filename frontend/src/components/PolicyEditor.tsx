import React, { useState } from "react";
import { updatePolicy } from "../api/client";

export default function PolicyEditor() {
  const [text, setText] = useState("{\n  \"policy_version\": 1,\n  \"rules\": []\n}");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const onSave = async () => {
    setError(null); setSuccess(null);
    try {
      const parsed = JSON.parse(text);
      const res = await updatePolicy(parsed);
      setSuccess("Policy updated");
    } catch (e: any) {
      setError(e?.message || "Invalid JSON");
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-2">Policy Editor</h2>
      {/* In a full setup, replace this textarea with Monaco editor */}
      <textarea
        className="w-full h-64 p-2 bg-black text-white border border-white/20 rounded"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <button onClick={onSave} className="px-3 py-1 bg-blue-600 text-white rounded">Save</button>
        {error && <span className="text-red-400">{error}</span>}
        {success && <span className="text-green-400">{success}</span>}
      </div>
    </div>
  );
}
