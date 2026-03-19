import { useEffect, useState } from "react";

function App() {
  const [data, setData] = useState("Loading...");

  useEffect(() => {
    fetch("http://127.0.0.1:8000")
      .then((res) => res.json())
      .then((data) => setData(JSON.stringify(data)))
      .catch((err) => setData("Error: " + err.message));
  }, []);

  return (
    <div style={{ textAlign: "center", marginTop: "50px" }}>
      <h1>Backend Response:</h1>
      <p>{data}</p>
    </div>
  );
}

export default App;