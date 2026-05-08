import { useEffect, useState } from 'react'
import { startAudit, fetchOrders, resumeOrder, type Order } from './api'
import { Flame, CheckCircle, AlertCircle, RefreshCcw, FileText } from 'lucide-react'

export default function App() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null); // New state for the file
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    const data = await fetchOrders();
    setOrders(data);
  };

  useEffect(() => { loadData(); }, []);

  const handleStart = async () => {
    if (!name || !file) return alert("Please provide a name and a PDF file");

    setLoading(true);

    // Create FormData to send the file to FastAPI
    const formData = new FormData();
    formData.append("customer_name", name);
    formData.append("file", file);

    await startAudit(formData); // Updated to pass formData

    setName("");
    setFile(null);
    // Reset the file input UI
    (document.getElementById('fileInput') as HTMLInputElement).value = "";

    await loadData();
    setLoading(false);
  };

  const handleResume = async (id: string, decision: string) => {
    await resumeOrder(id, decision);
    await loadData();
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8 font-sans">
      <header className="flex items-center gap-3 mb-12">
        <Flame className="text-orange-600 w-10 h-10" />
        <h1 className="text-3xl font-bold text-slate-800">Nate's Spicy Audit Dashboard</h1>
      </header>

      {/* Start New Audit Section */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 mb-12 grid grid-cols-1 md:grid-cols-3 gap-4">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Customer Name"
          className="border rounded-lg px-4 py-2 focus:ring-2 focus:ring-orange-500 outline-none"
        />

        {/* New File Input */}
        <div className="flex items-center gap-2 border rounded-lg px-4 py-2 bg-slate-50">
          <FileText className="text-slate-400" size={20} />
          <input
            id="fileInput"
            type="file"
            accept=".pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm text-slate-600"
          />
        </div>

        <button
          onClick={handleStart} disabled={loading}
          className="bg-orange-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-orange-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Analyzing..." : "Start Audit"}
        </button>
      </div>

      {/* Orders List */}
      <div className="grid gap-4">
        <div className="flex justify-between items-end">
          <h2 className="text-xl font-semibold text-slate-700">Audit History</h2>
          <button onClick={loadData} className="text-slate-400 hover:text-orange-600"><RefreshCcw size={20}/></button>
        </div>

        {orders.map(order => (
          <div key={order.id} className="bg-white p-5 rounded-lg border border-slate-200 flex items-center justify-between shadow-sm">
            <div>
              <p className="text-sm text-slate-400 font-mono mb-1">{order.id.slice(0,8)}...</p>
              <h3 className="text-lg font-bold text-slate-800">{order.customer_name}</h3>
              <p className="text-slate-500">{order.pepper_variety || "Analyzing..."}</p>
            </div>

            <div className="flex items-center gap-6">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                order.status === 'Completed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
              }`}>
                {order.status}
              </span>

              {order.status !== 'Completed' && (
                <div className="flex gap-2">
                  <button onClick={() => handleResume(order.id, "Approve")} className="p-2 text-green-600 hover:bg-green-50 rounded-lg"><CheckCircle/></button>
                  <button onClick={() => handleResume(order.id, "Reject")} className="p-2 text-red-600 hover:bg-red-50 rounded-lg"><AlertCircle/></button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
