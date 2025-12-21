import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import AuditLogsTable from './components/AuditLogsTable';
import PolicyEditor from './components/PolicyEditor';
import AttackLab from './components/AttackLab';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100 flex flex-col">
        <nav className="bg-white shadow-md p-4">
          <div className="max-w-7xl mx-auto flex justify-between items-center">
            <div className="flex items-center space-x-4">
              <h1 className="text-xl font-bold text-indigo-600">🔭 Vigil</h1>
              <div className="space-x-2">
                <Link to="/" className="px-3 py-2 rounded hover:bg-gray-100">Audit Logs</Link>
                <Link to="/policies" className="px-3 py-2 rounded hover:bg-gray-100">Policies</Link>
                <Link to="/attack-lab" className="px-3 py-2 rounded hover:bg-red-50 text-red-600 font-medium">Attack Lab 💥</Link>
              </div>
            </div>
            <div className="text-sm text-gray-500">
              Connected to AgentShield Core
            </div>
          </div>
        </nav>

        <main className="flex-grow p-8 max-w-7xl mx-auto w-full">
          <Routes>
            <Route path="/" element={<AuditLogsTable />} />
            <Route path="/policies" element={<PolicyEditor />} />
            <Route path="/attack-lab" element={<AttackLab />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
