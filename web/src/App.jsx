import { useEffect, useState } from "react";

const EMPTY = {
  fund_id: "",
  fund_name: "",
  manager: "",
  strategy: "",
  vintage_year: "",
  commitment: "",
  reported_at: "",
};

const FIELDS = [
  ["fund_id", "Fund ID", "text"],
  ["fund_name", "Name", "text"],
  ["manager", "Manager", "text"],
  ["strategy", "Strategy", "text"],
  ["vintage_year", "Vintage", "number"],
  ["commitment", "Commitment", "text"],
  ["reported_at", "Reported", "date"],
];

async function saveFund(fund, editing) {
  const response = await fetch(editing ? `/funds/${fund.fund_id}` : "/funds", {
    method: editing ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...fund, vintage_year: Number(fund.vintage_year) }),
  });
  const body = await response.json();
  if (!response.ok) {
    // FastAPI sends a string for HTTPException, a list of errors for validation.
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : body.detail.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("; ")
    );
  }
  return body;
}

export default function App() {
  const [funds, setFunds] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);

  const load = () =>
    fetch("/funds")
      .then((r) => r.json())
      .then(setFunds)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const reset = () => {
    setForm(EMPTY);
    setEditing(false);
    setError(null);
  };

  const submit = async (event) => {
    event.preventDefault();
    try {
      await saveFund(form, editing);
      reset();
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const edit = (fund) => {
    setForm(fund);
    setEditing(true);
    setError(null);
  };

  return (
    <main>
      <h1>Funds</h1>

      <form onSubmit={submit}>
        <h2>{editing ? `Edit ${form.fund_id}` : "Add fund"}</h2>
        {FIELDS.map(([name, label, type]) => (
          <label key={name}>
            {label}
            <input
              type={type}
              value={form[name]}
              required={name !== "commitment"}
              disabled={editing && name === "fund_id"}
              onChange={(e) => setForm({ ...form, [name]: e.target.value })}
            />
          </label>
        ))}
        <div className="actions">
          <button type="submit">{editing ? "Save" : "Add"}</button>
          {editing && (
            <button type="button" onClick={reset}>
              Cancel
            </button>
          )}
        </div>
        {error && <p className="error">{error}</p>}
      </form>

      <p>{funds.length} funds</p>
      <table>
        <thead>
          <tr>
            {FIELDS.map(([name, label]) => (
              <th key={name}>{label}</th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {funds.map((fund) => (
            <tr key={fund.fund_id}>
              {FIELDS.map(([name]) => (
                <td key={name}>{fund[name]}</td>
              ))}
              <td>
                <button type="button" onClick={() => edit(fund)}>
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
