import { useState, useEffect, useRef, useCallback } from "react";
import { useAmbulatorio, apiClient } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  MessageCircle, 
  Send, 
  X, 
  Mic, 
  MicOff, 
  Trash2, 
  Plus,
  Bot,
  User,
  Loader2,
  History,
  Volume2,
  GripHorizontal,
  Download,
  Minimize2,
  Maximize2,
  Image,
  Upload,
  Check
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export default function AIAssistant() {
  const { ambulatorio } = useAmbulatorio();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [showSessions, setShowSessions] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  
  // Drag state
  const [position, setPosition] = useState({ x: null, y: null });
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  
  // Image upload state
  const [pendingImage, setPendingImage] = useState(null);
  const [extractedPatients, setExtractedPatients] = useState([]);
  const [isExtracting, setIsExtracting] = useState(false);
  const fileInputRef = useRef(null);
  
  // NUOVO: Memoria contestuale e workflow
  const [contextMemory, setContextMemory] = useState({
    lastPatient: null,        // Ultimo paziente menzionato
    lastAction: null,         // Ultima azione eseguita
    workflowStep: null,       // Step corrente del workflow
    workflowType: null        // Tipo di workflow attivo
  });
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [activeWorkflow, setActiveWorkflow] = useState(null);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const chatRef = useRef(null);

  // Suggerimenti intelligenti basati sul contesto
  const getSmartSuggestions = () => {
    const { lastPatient, lastAction } = contextMemory;
    
    // Se c'è un paziente in memoria, suggerisci azioni su di lui
    if (lastPatient) {
      const patientName = `${lastPatient.cognome} ${lastPatient.nome}`;
      const isPICC = lastPatient.tipo === "PICC" || lastPatient.tipo === "PICC_MED";
      const isMED = lastPatient.tipo === "MED" || lastPatient.tipo === "PICC_MED";
      
      return [
        { label: `📅 Appuntamento ${lastPatient.cognome}`, action: `Crea appuntamento per ${patientName} domani mattina` },
        isPICC && { label: `📋 Copia scheda PICC`, action: `${patientName} copia ultima scheda gestione picc data di oggi` },
        isMED && { label: `📋 Copia scheda MED`, action: `${patientName} copia ultima scheda medicazione med data di oggi` },
        { label: `📄 Stampa cartella`, action: `Stampa cartella clinica di ${patientName}` },
        { label: `🔄 Altro paziente`, action: null, clear: true }
      ].filter(Boolean);
    }
    
    // Suggerimenti generali
    return [
      { label: "➕ Nuovo paziente", action: null, workflow: "new_patient" },
      { label: "📅 Nuovo appuntamento", action: null, workflow: "new_appointment" },
      { label: "📊 Statistiche mese", action: "Quante prestazioni ho fatto questo mese?" },
      { label: "📋 Copia scheda", action: null, workflow: "copy_scheda" },
      { label: "🔍 Cerca paziente", action: null, workflow: "search_patient" }
    ];
  };

  // Workflow guidati
  const workflows = {
    new_patient: {
      title: "Nuovo Paziente",
      steps: [
        { prompt: "Come si chiama il paziente? (Cognome Nome)", field: "nome" },
        { prompt: "Che tipo di paziente è?", options: ["PICC", "MED", "PICC + MED"], field: "tipo" },
        { prompt: "Codice fiscale (opzionale, premi Invio per saltare)", field: "cf", optional: true }
      ],
      buildAction: (data) => `Crea paziente ${data.nome} tipo ${data.tipo}${data.cf ? ` codice fiscale ${data.cf}` : ''}`
    },
    new_appointment: {
      title: "Nuovo Appuntamento",
      steps: [
        { prompt: "Per quale paziente? (Cognome Nome)", field: "paziente" },
        { prompt: "Quando?", options: ["Oggi", "Domani", "Dopodomani", "Scrivi data..."], field: "data" },
        { prompt: "Mattina o pomeriggio?", options: ["Mattina (8:00-12:00)", "Pomeriggio (15:00-18:00)"], field: "turno" }
      ],
      buildAction: (data) => {
        const turno = data.turno.includes("Mattina") ? "mattina" : "pomeriggio";
        return `Crea appuntamento per ${data.paziente} ${data.data.toLowerCase()} ${turno}`;
      }
    },
    copy_scheda: {
      title: "Copia Scheda Medicazione",
      steps: [
        { prompt: "Per quale paziente?", field: "paziente" },
        { prompt: "Tipo di scheda?", options: ["Gestione PICC", "Medicazione MED"], field: "tipo_scheda" },
        { prompt: "Con quale data?", options: ["Oggi", "Domani", "Scrivi data..."], field: "data" }
      ],
      buildAction: (data) => {
        const scheda = data.tipo_scheda.includes("PICC") ? "gestione picc" : "medicazione med";
        return `${data.paziente} copia ultima scheda ${scheda} data di ${data.data.toLowerCase()}`;
      }
    },
    search_patient: {
      title: "Cerca Paziente",
      steps: [
        { prompt: "Scrivi il nome del paziente da cercare", field: "nome" }
      ],
      buildAction: (data) => `Cerca paziente ${data.nome}`
    }
  };

  const [workflowData, setWorkflowData] = useState({});
  const [currentWorkflowStep, setCurrentWorkflowStep] = useState(0);

  const startWorkflow = (workflowType) => {
    const workflow = workflows[workflowType];
    if (!workflow) return;
    
    setActiveWorkflow(workflowType);
    setWorkflowData({});
    setCurrentWorkflowStep(0);
    setShowSuggestions(false);
    
    const firstStep = workflow.steps[0];
    setMessages(prev => [...prev, {
      role: "assistant",
      content: `🔄 **${workflow.title}** - Step 1/${workflow.steps.length}\n\n${firstStep.prompt}`,
      workflowOptions: firstStep.options
    }]);
  };

  const handleWorkflowInput = (input) => {
    if (!activeWorkflow) return false;
    
    const workflow = workflows[activeWorkflow];
    const currentStep = workflow.steps[currentWorkflowStep];
    
    // Salva il dato
    const newData = { ...workflowData, [currentStep.field]: input };
    setWorkflowData(newData);
    
    // Prossimo step o completa
    if (currentWorkflowStep < workflow.steps.length - 1) {
      const nextStep = workflow.steps[currentWorkflowStep + 1];
      setCurrentWorkflowStep(prev => prev + 1);
      
      setMessages(prev => [...prev, 
        { role: "user", content: input },
        { 
          role: "assistant", 
          content: `✅ **${workflow.title}** - Step ${currentWorkflowStep + 2}/${workflow.steps.length}\n\n${nextStep.prompt}`,
          workflowOptions: nextStep.options
        }
      ]);
      return true;
    } else {
      // Workflow completato - esegui azione
      const action = workflow.buildAction(newData);
      setActiveWorkflow(null);
      setWorkflowData({});
      setCurrentWorkflowStep(0);
      setShowSuggestions(true);
      
      // Invia il comando all'IA
      setInputValue(action);
      setTimeout(() => {
        setMessages(prev => [...prev, { role: "user", content: input }]);
        sendMessageDirect(action);
      }, 100);
      return true;
    }
  };

  // Invia messaggio direttamente (per workflow)
  const sendMessageDirect = async (message) => {
    setIsLoading(true);
    try {
      const response = await apiClient.post("/ai/chat", {
        message,
        session_id: sessionId,
        ambulatorio
      });

      const { response: aiResponse, session_id: newSessionId, action_performed } = response.data;
      
      if (!sessionId) setSessionId(newSessionId);

      // Aggiorna memoria contestuale
      if (action_performed?.patient) {
        setContextMemory(prev => ({
          ...prev,
          lastPatient: action_performed.patient,
          lastAction: action_performed.action_type
        }));
      }

      const hasPdf = action_performed?.pdf_url || action_performed?.pdf_endpoint;
      
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: aiResponse,
        pdfData: hasPdf ? action_performed : null
      }]);

      if (action_performed?.navigate_to) {
        toast.success("Apertura in corso...");
        setTimeout(() => navigate(action_performed.navigate_to), 1000);
      }

      loadSessions();
    } catch (error) {
      console.error("Chat error:", error);
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: "Mi dispiace, ho avuto un problema. Riprova." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Gestisci click su suggerimento
  const handleSuggestionClick = (suggestion) => {
    if (suggestion.clear) {
      setContextMemory({ lastPatient: null, lastAction: null, workflowStep: null, workflowType: null });
      setMessages(prev => [...prev, { role: "assistant", content: "✨ Ok! Come posso aiutarti?" }]);
      return;
    }
    
    if (suggestion.workflow) {
      startWorkflow(suggestion.workflow);
      return;
    }
    
    if (suggestion.action) {
      setInputValue(suggestion.action);
      setTimeout(() => sendMessage(), 100);
    }
  };
  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'it-IT';

      recognitionRef.current.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(result => result[0].transcript)
          .join('');
        setInputValue(transcript);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
        toast.error("Errore nel riconoscimento vocale");
      };
    }
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load sessions when opened
  useEffect(() => {
    if (isOpen && ambulatorio) {
      loadSessions();
    }
  }, [isOpen, ambulatorio]);

  // Drag handlers
  const handleMouseDown = (e) => {
    if (e.target.closest('.drag-handle')) {
      setIsDragging(true);
      const rect = chatRef.current.getBoundingClientRect();
      setDragOffset({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      });
    }
  };

  const handleMouseMove = useCallback((e) => {
    if (isDragging && chatRef.current) {
      const newX = e.clientX - dragOffset.x;
      const newY = e.clientY - dragOffset.y;
      
      // Keep within bounds
      const maxX = window.innerWidth - chatRef.current.offsetWidth;
      const maxY = window.innerHeight - chatRef.current.offsetHeight;
      
      setPosition({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY))
      });
    }
  }, [isDragging, dragOffset]);

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove]);

  // Touch handlers for mobile
  const handleTouchStart = (e) => {
    if (e.target.closest('.drag-handle')) {
      const touch = e.touches[0];
      setIsDragging(true);
      const rect = chatRef.current.getBoundingClientRect();
      setDragOffset({
        x: touch.clientX - rect.left,
        y: touch.clientY - rect.top
      });
    }
  };

  const handleTouchMove = useCallback((e) => {
    if (isDragging && chatRef.current) {
      const touch = e.touches[0];
      const newX = touch.clientX - dragOffset.x;
      const newY = touch.clientY - dragOffset.y;
      
      const maxX = window.innerWidth - chatRef.current.offsetWidth;
      const maxY = window.innerHeight - chatRef.current.offsetHeight;
      
      setPosition({
        x: Math.max(0, Math.min(newX, maxX)),
        y: Math.max(0, Math.min(newY, maxY))
      });
    }
  }, [isDragging, dragOffset]);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('touchmove', handleTouchMove);
      window.addEventListener('touchend', handleMouseUp);
    }
    return () => {
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleMouseUp);
    };
  }, [isDragging, handleTouchMove]);

  const loadSessions = async () => {
    try {
      const response = await apiClient.get("/ai/sessions", {
        params: { ambulatorio }
      });
      setSessions(response.data);
    } catch (error) {
      console.error("Error loading sessions:", error);
    }
  };

  const loadSession = async (sid) => {
    try {
      const response = await apiClient.get("/ai/history", {
        params: { ambulatorio, session_id: sid }
      });
      if (response.data.length > 0) {
        const sessionMessages = response.data[0].messages.reverse();
        setMessages(sessionMessages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp
        })));
        setSessionId(sid);
      }
      setShowSessions(false);
    } catch (error) {
      console.error("Error loading chat session:", error);
      if (error.code === 'ERR_NETWORK') {
        toast.error("Errore di connessione al server");
      }
      // Silently handle other errors
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setShowSessions(false);
  };

  const deleteSession = async (sid, e) => {
    e.stopPropagation();
    try {
      await apiClient.delete(`/ai/session/${sid}`, {
        params: { ambulatorio }
      });
      setSessions(sessions.filter(s => s.session_id !== sid));
      if (sessionId === sid) {
        startNewChat();
      }
      toast.success("Chat eliminata");
    } catch (error) {
      toast.error("Errore nell'eliminazione");
    }
  };

  const clearAllHistory = async () => {
    try {
      await apiClient.delete("/ai/history", {
        params: { ambulatorio }
      });
      setSessions([]);
      startNewChat();
      toast.success("Cronologia eliminata");
    } catch (error) {
      toast.error("Errore nell'eliminazione");
    }
  };

  const toggleListening = () => {
    if (!recognitionRef.current) {
      toast.error("Riconoscimento vocale non supportato");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const speakResponse = (text) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      // Remove markdown formatting for speech
      const cleanText = text.replace(/\*\*/g, '').replace(/\n/g, '. ');
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = 'it-IT';
      utterance.rate = 1;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
    }
  };

  const downloadPdf = async (pdfData) => {
    if (pdfData?.pdf_url) {
      window.open(pdfData.pdf_url, '_blank');
    } else if (pdfData?.pdf_endpoint) {
      try {
        const response = await apiClient.get(pdfData.pdf_endpoint, { responseType: 'blob' });
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', pdfData.filename || 'report.pdf');
        document.body.appendChild(link);
        link.click();
        link.remove();
        toast.success("PDF scaricato!");
      } catch (error) {
        toast.error("Errore nel download del PDF");
      }
    }
  };

  // Image upload and extraction
  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        toast.error("Seleziona un'immagine valida (JPG, PNG, WEBP)");
        return;
      }
      setPendingImage(file);
      setExtractedPatients([]);
      toast.success("Immagine selezionata. Scrivi il tipo di paziente (es. 'aggiungi come PICC') o clicca 'Estrai' per iniziare.");
    }
  };

  const extractPatientsFromImage = async (tipoDefault = "PICC") => {
    if (!pendingImage) {
      toast.error("Prima seleziona un'immagine");
      return;
    }

    setIsExtracting(true);
    
    try {
      const formData = new FormData();
      formData.append('file', pendingImage);
      formData.append('ambulatorio', ambulatorio);
      formData.append('tipo_default', tipoDefault);
      
      const response = await apiClient.post("/ai/extract-from-image", formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      if (response.data.patients && response.data.patients.length > 0) {
        setExtractedPatients(response.data.patients);
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `📷 **Estratti ${response.data.count} pazienti dall'immagine:**\n\n${response.data.patients.map(p => `• ${p.cognome} ${p.nome}`).join('\n')}\n\n✅ Scrivi "**conferma**" per aggiungerli come ${tipoDefault}, oppure "**annulla**" per cancellare.`,
          extractedPatients: response.data.patients,
          tipoDefault: tipoDefault
        }]);
      } else {
        toast.warning("Nessun nome trovato nell'immagine");
        setMessages(prev => [...prev, {
          role: "assistant",
          content: "❌ Non sono riuscito a identificare nomi di pazienti nell'immagine. Prova con un'immagine più chiara o scrivi i nomi manualmente."
        }]);
      }
    } catch (error) {
      console.error("Extraction error:", error);
      toast.error("Errore nell'estrazione");
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "❌ Errore nell'estrazione dei nomi dall'immagine. Riprova."
      }]);
    } finally {
      setIsExtracting(false);
    }
  };

  const confirmExtractedPatients = async (patients, tipo) => {
    try {
      const response = await apiClient.post("/patients/batch", {
        patients: patients.map(p => ({
          ...p,
          ambulatorio,
          tipo: p.tipo || tipo
        }))
      });
      
      if (response.data.created > 0) {
        toast.success(`${response.data.created} pazienti creati!`);
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `✅ **Creati ${response.data.created} pazienti!**\n\n${patients.map(p => `• ${p.cognome} ${p.nome} (${p.tipo || tipo})`).join('\n')}`
        }]);
      }
      if (response.data.errors > 0) {
        toast.warning(`${response.data.errors} pazienti non creati`);
      }
      
      setExtractedPatients([]);
      setPendingImage(null);
    } catch (error) {
      toast.error("Errore nella creazione dei pazienti");
    }
  };

  const clearPendingImage = () => {
    setPendingImage(null);
    setExtractedPatients([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
    
    // Check if user is confirming extracted patients
    const lowerMsg = userMessage.toLowerCase();
    if (extractedPatients.length > 0) {
      if (lowerMsg.includes("conferma") || lowerMsg.includes("sì") || lowerMsg.includes("si") || lowerMsg.includes("ok")) {
        // Get tipo from last assistant message or default
        const lastAssistantMsg = messages.filter(m => m.role === "assistant" && m.tipoDefault).pop();
        const tipo = lastAssistantMsg?.tipoDefault || "PICC";
        await confirmExtractedPatients(extractedPatients, tipo);
        return;
      } else if (lowerMsg.includes("annulla") || lowerMsg.includes("no")) {
        setExtractedPatients([]);
        setPendingImage(null);
        setMessages(prev => [...prev, { role: "assistant", content: "❌ Operazione annullata. I pazienti non sono stati aggiunti." }]);
        return;
      }
    }
    
    // Check if user wants to extract from pending image with specific type
    if (pendingImage && (lowerMsg.includes("picc") || lowerMsg.includes("med") || lowerMsg.includes("estrai") || lowerMsg.includes("aggiungi"))) {
      let tipo = "PICC";
      if (lowerMsg.includes("med") && !lowerMsg.includes("picc")) {
        tipo = "MED";
      } else if (lowerMsg.includes("picc") && lowerMsg.includes("med")) {
        tipo = "PICC_MED";
      }
      await extractPatientsFromImage(tipo);
      return;
    }
    
    setIsLoading(true);

    try {
      const response = await apiClient.post("/ai/chat", {
        message: userMessage,
        session_id: sessionId,
        ambulatorio
      });

      const { response: aiResponse, session_id: newSessionId, action_performed } = response.data;
      
      if (!sessionId) {
        setSessionId(newSessionId);
      }

      // Check for PDF download offer
      const hasPdf = action_performed?.pdf_url || action_performed?.pdf_endpoint;
      
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: aiResponse,
        pdfData: hasPdf ? action_performed : null
      }]);

      // Handle navigation if action requires it
      if (action_performed?.navigate_to) {
        toast.success("Apertura in corso...");
        setTimeout(() => {
          navigate(action_performed.navigate_to);
        }, 1000);
      }

      loadSessions();
    } catch (error) {
      console.error("Chat error:", error);
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: "Mi dispiace, ho avuto un problema di connessione. Riprova tra poco." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const resetPosition = () => {
    setPosition({ x: null, y: null });
  };

  if (!ambulatorio) return null;

  // Calculate position style
  const positionStyle = position.x !== null ? {
    left: position.x,
    top: position.y,
    right: 'auto',
    bottom: 'auto'
  } : {
    right: 24,
    bottom: 24
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => { setIsOpen(true); setIsMinimized(false); }}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center ${isOpen ? 'scale-0' : 'scale-100'}`}
        data-testid="ai-assistant-btn"
      >
        <MessageCircle className="w-6 h-6" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full animate-pulse"></span>
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div 
          ref={chatRef}
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
          style={positionStyle}
          className={`fixed z-50 bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-200 ${isDragging ? 'cursor-grabbing' : ''} ${isMinimized ? 'w-[300px] h-[60px]' : 'w-[420px] h-[600px] max-h-[80vh]'}`}
          data-testid="ai-chat-window"
        >
          {/* Header with drag handle */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-3 flex items-center justify-between select-none">
            <div className="flex items-center gap-2 flex-1">
              {/* Drag Handle */}
              <div className="drag-handle cursor-grab active:cursor-grabbing p-1 hover:bg-white/20 rounded">
                <GripHorizontal className="w-5 h-5" />
              </div>
              <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-sm">Assistente IA</h3>
                {!isMinimized && <p className="text-xs text-blue-100">Trascina per spostare</p>}
              </div>
            </div>
            <div className="flex items-center gap-1">
              {!isMinimized && (
                <>
                  <button
                    onClick={() => setShowSessions(!showSessions)}
                    className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                    title="Cronologia"
                  >
                    <History className="w-4 h-4" />
                  </button>
                  <button
                    onClick={startNewChat}
                    className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                    title="Nuova chat"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  {position.x !== null && (
                    <button
                      onClick={resetPosition}
                      className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                      title="Ripristina posizione"
                    >
                      <Maximize2 className="w-4 h-4" />
                    </button>
                  )}
                </>
              )}
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                title={isMinimized ? "Espandi" : "Riduci"}
              >
                {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {!isMinimized && (
            <>
              {/* Sessions Panel */}
              {showSessions && (
                <div className="absolute top-14 left-0 right-0 bg-white border-b shadow-lg z-10 max-h-64 overflow-auto">
                  <div className="p-3 border-b flex justify-between items-center">
                    <span className="font-medium text-sm">Cronologia Chat</span>
                    {sessions.length > 0 && (
                      <button
                        onClick={clearAllHistory}
                        className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        Elimina tutto
                      </button>
                    )}
                  </div>
                  {sessions.length === 0 ? (
                    <p className="p-4 text-sm text-gray-500 text-center">Nessuna chat precedente</p>
                  ) : (
                    sessions.map((session) => (
                      <div
                        key={session.session_id}
                        onClick={() => loadSession(session.session_id)}
                        className={`p-3 hover:bg-gray-50 cursor-pointer flex justify-between items-center border-b ${sessionId === session.session_id ? 'bg-blue-50' : ''}`}
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm truncate">{session.last_message}</p>
                          <p className="text-xs text-gray-400">{new Date(session.last_timestamp).toLocaleDateString('it-IT')}</p>
                        </div>
                        <button
                          onClick={(e) => deleteSession(session.session_id, e)}
                          className="p-1 text-gray-400 hover:text-red-500 ml-2"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Messages */}
              <ScrollArea className="flex-1 p-4">
                {messages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center p-4">
                    <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center mb-3">
                      <Bot className="w-7 h-7 text-blue-600" />
                    </div>
                    <h4 className="font-semibold text-gray-800 mb-2">Ciao! Come posso aiutarti?</h4>
                    <p className="text-xs text-gray-500 mb-3">Gestisco pazienti, appuntamenti, statistiche e PDF</p>
                    <div className="space-y-1.5 text-xs text-gray-400 text-left">
                      <p>💡 "Appuntamento per Rossi alle 15 di domani"</p>
                      <p>💡 "Crea pazienti: Rossi Mario PICC, Bianchi Luigi MED"</p>
                      <p>💡 "Sospendi Rossi, Bianchi e Verdi"</p>
                      <p>💡 "Dimetti tutti: Rossi, Bianchi, Neri"</p>
                      <p>📷 "Carica foto con nomi e scrivi 'aggiungi come PICC'"</p>
                      <p>💡 "Quanti PICC ho impiantato a maggio?"</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {messages.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div className={`flex items-start gap-2 max-w-[90%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'user' ? 'bg-blue-600' : 'bg-gray-200'}`}>
                            {msg.role === 'user' ? (
                              <User className="w-4 h-4 text-white" />
                            ) : (
                              <Bot className="w-4 h-4 text-gray-600" />
                            )}
                          </div>
                          <div className={`rounded-2xl px-3 py-2 ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-800'}`}>
                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                            {msg.role === 'assistant' && (
                              <div className="mt-1 flex items-center gap-2">
                                <button
                                  onClick={() => speakResponse(msg.content)}
                                  className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                                >
                                  <Volume2 className="w-3 h-3" />
                                  {isSpeaking ? 'Stop' : 'Ascolta'}
                                </button>
                                {msg.pdfData && (
                                  <button
                                    onClick={() => downloadPdf(msg.pdfData)}
                                    className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                                  >
                                    <Download className="w-3 h-3" />
                                    Scarica PDF
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                    {isLoading && (
                      <div className="flex justify-start">
                        <div className="flex items-start gap-2">
                          <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center">
                            <Bot className="w-4 h-4 text-gray-600" />
                          </div>
                          <div className="bg-gray-100 rounded-2xl px-4 py-3">
                            <div className="flex gap-1">
                              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                              <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </ScrollArea>

              {/* Input */}
              <div className="p-3 border-t bg-gray-50">
                {/* Pending Image Preview */}
                {pendingImage && (
                  <div className="mb-2 p-2 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-2">
                    <Image className="w-4 h-4 text-blue-600" />
                    <span className="text-xs text-blue-700 flex-1 truncate">{pendingImage.name}</span>
                    {isExtracting ? (
                      <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                    ) : (
                      <>
                        <button
                          onClick={() => extractPatientsFromImage("PICC")}
                          className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                          Estrai
                        </button>
                        <button
                          onClick={clearPendingImage}
                          className="text-red-500 hover:text-red-700"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </>
                    )}
                  </div>
                )}
                
                {/* Extracted Patients Confirmation */}
                {extractedPatients.length > 0 && (
                  <div className="mb-2 p-2 bg-green-50 border border-green-200 rounded-lg">
                    <div className="text-xs text-green-700 mb-1">
                      <Check className="w-3 h-3 inline mr-1" />
                      {extractedPatients.length} pazienti estratti
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => confirmExtractedPatients(extractedPatients, "PICC")}
                        className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                      >
                        Conferma PICC
                      </button>
                      <button
                        onClick={() => confirmExtractedPatients(extractedPatients, "MED")}
                        className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Conferma MED
                      </button>
                      <button
                        onClick={clearPendingImage}
                        className="text-xs px-2 py-1 text-red-600 hover:text-red-700"
                      >
                        Annulla
                      </button>
                    </div>
                  </div>
                )}
                
                <div className="flex items-center gap-2">
                  {/* Image Upload Button */}
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept="image/*"
                    onChange={handleImageSelect}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className={`p-2.5 rounded-full transition-colors ${pendingImage ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                    title="Carica foto con nomi pazienti"
                    disabled={isExtracting}
                  >
                    <Image className="w-4 h-4" />
                  </button>
                  <button
                    onClick={toggleListening}
                    className={`p-2.5 rounded-full transition-colors ${isListening ? 'bg-red-500 text-white animate-pulse' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                    title={isListening ? "Ferma registrazione" : "Parla"}
                  >
                    {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                  </button>
                  <Input
                    ref={inputRef}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={isListening ? "Sto ascoltando..." : pendingImage ? "Scrivi 'aggiungi come PICC' o 'aggiungi come MED'..." : "Scrivi un messaggio..."}
                    className="flex-1 rounded-full border-gray-200 text-sm"
                    disabled={isLoading || isExtracting}
                    data-testid="ai-chat-input"
                  />
                  <Button
                    onClick={sendMessage}
                    disabled={!inputValue.trim() || isLoading || isExtracting}
                    className="rounded-full w-10 h-10 p-0 bg-blue-600 hover:bg-blue-700"
                    data-testid="ai-send-btn"
                  >
                    {isLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Send className="w-4 h-4" />
                    )}
                  </Button>
                </div>
                {isListening && (
                  <p className="text-xs text-center text-red-500 mt-1 animate-pulse">
                    🎤 Registrazione in corso...
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
