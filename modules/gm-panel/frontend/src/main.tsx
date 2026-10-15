import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// Sem StrictMode: o mapa cria um contexto WebGL e montá-lo duas vezes em desenvolvimento não acrescenta nada.
createRoot(document.getElementById("root")!).render(<App />);
