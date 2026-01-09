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
  ChevronDown,
  Loader2,
  History,
  Volume2
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

export default function AIAssistant() {
  const { ambulatorio } = useAmbulatorio();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [showSessions, setShowSessions] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  // Initialize speech recognition
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
      toast.error("Errore nel caricamento della chat");
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
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'it-IT';
      utterance.rate = 1;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setMessages(prev => [...prev, { role: "user", content: userMessage }]);
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

      setMessages(prev => [...prev, { role: "assistant", content: aiResponse }]);

      // Handle navigation if action requires it
      if (action_performed?.navigate_to) {
        toast.success("Apertura cartella paziente...");
        setTimeout(() => {
          navigate(action_performed.navigate_to);
          setIsOpen(false);
        }, 1000);
      }

      // Auto-speak response (optional - can be toggled)
      // speakResponse(aiResponse);

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

  if (!ambulatorio) return null;

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(true)}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center ${isOpen ? 'scale-0' : 'scale-100'}`}
        data-testid="ai-assistant-btn"
      >
        <MessageCircle className="w-6 h-6" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full animate-pulse"></span>
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 w-[400px] h-[600px] max-h-[80vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-gray-200 animate-in slide-in-from-bottom-5 duration-300" data-testid="ai-chat-window">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                <Bot className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold">Assistente IA</h3>
                <p className="text-xs text-blue-100">Sempre pronto ad aiutarti</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSessions(!showSessions)}
                className="p-2 hover:bg-white/20 rounded-full transition-colors"
                title="Cronologia"
              >
                <History className="w-5 h-5" />
              </button>
              <button
                onClick={startNewChat}
                className="p-2 hover:bg-white/20 rounded-full transition-colors"
                title="Nuova chat"
              >
                <Plus className="w-5 h-5" />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 hover:bg-white/20 rounded-full transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Sessions Panel */}
          {showSessions && (
            <div className="absolute top-16 left-0 right-0 bg-white border-b shadow-lg z-10 max-h-64 overflow-auto">
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
              <div className="h-full flex flex-col items-center justify-center text-center p-6">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                  <Bot className="w-8 h-8 text-blue-600" />
                </div>
                <h4 className="font-semibold text-gray-800 mb-2">Ciao! Come posso aiutarti?</h4>
                <p className="text-sm text-gray-500 mb-4">Posso creare pazienti, prendere appuntamenti, consultare statistiche e molto altro!</p>
                <div className="space-y-2 text-xs text-gray-400">
                  <p>💡 "Crea paziente PICC Mario Rossi"</p>
                  <p>💡 "Quanti PICC ho impiantato a dicembre?"</p>
                  <p>💡 "Dai appuntamento a Rossi per giovedì"</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`flex items-start gap-2 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'user' ? 'bg-blue-600' : 'bg-gray-200'}`}>
                        {msg.role === 'user' ? (
                          <User className="w-4 h-4 text-white" />
                        ) : (
                          <Bot className="w-4 h-4 text-gray-600" />
                        )}
                      </div>
                      <div className={`rounded-2xl px-4 py-2 ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-800'}`}>
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        {msg.role === 'assistant' && (
                          <button
                            onClick={() => speakResponse(msg.content)}
                            className="mt-1 text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                          >
                            <Volume2 className="w-3 h-3" />
                            {isSpeaking ? 'Parlando...' : 'Ascolta'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="flex items-start gap-2">
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
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
          <div className="p-4 border-t bg-gray-50">
            <div className="flex items-center gap-2">
              <button
                onClick={toggleListening}
                className={`p-3 rounded-full transition-colors ${isListening ? 'bg-red-500 text-white animate-pulse' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                title={isListening ? "Ferma registrazione" : "Parla"}
              >
                {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
              </button>
              <Input
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isListening ? "Sto ascoltando..." : "Scrivi un messaggio..."}
                className="flex-1 rounded-full border-gray-200"
                disabled={isLoading}
                data-testid="ai-chat-input"
              />
              <Button
                onClick={sendMessage}
                disabled={!inputValue.trim() || isLoading}
                className="rounded-full w-12 h-12 p-0 bg-blue-600 hover:bg-blue-700"
                data-testid="ai-send-btn"
              >
                {isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </div>
            {isListening && (
              <p className="text-xs text-center text-red-500 mt-2 animate-pulse">
                🎤 Registrazione in corso... Parla ora
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
