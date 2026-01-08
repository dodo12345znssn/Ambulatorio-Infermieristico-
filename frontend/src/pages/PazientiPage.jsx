import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAmbulatorio, apiClient } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Search,
  Plus,
  Users,
  UserCheck,
  UserX,
  ChevronRight,
  MoreVertical,
  Pause,
  Play,
  Trash2,
  Filter,
  ChevronDown,
} from "lucide-react";
import { toast } from "sonner";

const PATIENT_TYPES = [
  { value: "PICC", label: "PICC", color: "bg-emerald-100 text-emerald-700" },
  { value: "MED", label: "MED", color: "bg-blue-100 text-blue-700" },
  { value: "PICC_MED", label: "PICC + MED", color: "bg-purple-100 text-purple-700" },
];

// Simple custom select component without portal issues
const SimpleSelect = ({ value, onChange, options, placeholder, className = "" }) => {
  const [isOpen, setIsOpen] = useState(false);
  const selectRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (selectRef.current && !selectRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find(opt => opt.value === value);

  return (
    <div ref={selectRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      >
        <span className={selectedOption ? "" : "text-muted-foreground"}>
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown className={`h-4 w-4 opacity-50 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover text-popover-foreground shadow-md max-h-60 overflow-auto">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`w-full px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground ${
                value === option.value ? 'bg-accent/50' : ''
              }`}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// Simple dropdown menu without portal issues
const SimpleDropdown = ({ trigger, children, align = "end" }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={dropdownRef} className="relative">
      <div onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}>
        {trigger}
      </div>
      {isOpen && (
        <div 
          className={`absolute z-50 mt-1 min-w-[180px] rounded-md border bg-popover p-1 text-popover-foreground shadow-md ${
            align === "end" ? "right-0" : "left-0"
          }`}
          onClick={() => setIsOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
};

const DropdownItem = ({ onClick, icon: Icon, children, className = "" }) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground ${className}`}
  >
    {Icon && <Icon className="w-4 h-4 mr-2" />}
    {children}
  </button>
);

const DropdownSeparator = () => <div className="my-1 h-px bg-muted" />;

export default function PazientiPage() {
  const { ambulatorio } = useAmbulatorio();
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [allPatients, setAllPatients] = useState({ in_cura: [], dimesso: [], sospeso: [] });
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("in_cura");
  const [typeFilter, setTypeFilter] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedPatientForStatus, setSelectedPatientForStatus] = useState(null);
  const [selectedPatientForDelete, setSelectedPatientForDelete] = useState(null);
  const [newStatus, setNewStatus] = useState("");
  const [statusReason, setStatusReason] = useState("");
  const [statusNotes, setStatusNotes] = useState("");
  const [newPatient, setNewPatient] = useState({
    nome: "",
    cognome: "",
    tipo: "",
  });

  const isVillaGinestre = ambulatorio === "villa_ginestre";
  const availableTypes = isVillaGinestre 
    ? PATIENT_TYPES.filter(t => t.value === "PICC")
    : PATIENT_TYPES;

  // Options for selects
  const typeFilterOptions = [
    { value: "all", label: "Tutti i tipi" },
    { value: "PICC", label: "Solo PICC" },
    { value: "MED", label: "Solo MED" },
    { value: "PICC_MED", label: "Solo PICC+MED" },
  ];

  const patientTypeOptions = availableTypes.map(t => ({ value: t.value, label: t.label }));

  const dischargeReasonOptions = [
    { value: "guarito", label: "Guarito" },
    { value: "adi", label: "ADI" },
    { value: "altro", label: "Altro" },
  ];

  const fetchAllPatients = useCallback(async () => {
    setLoading(true);
    try {
      const [inCuraRes, dimessiRes, sospesiRes] = await Promise.all([
        apiClient.get("/patients", { params: { ambulatorio, status: "in_cura" } }),
        apiClient.get("/patients", { params: { ambulatorio, status: "dimesso" } }),
        apiClient.get("/patients", { params: { ambulatorio, status: "sospeso" } }),
      ]);
      
      setAllPatients({
        in_cura: inCuraRes.data,
        dimesso: dimessiRes.data,
        sospeso: sospesiRes.data,
      });
    } catch (error) {
      toast.error("Errore nel caricamento dei pazienti");
    } finally {
      setLoading(false);
    }
  }, [ambulatorio]);

  useEffect(() => {
    fetchAllPatients();
  }, [fetchAllPatients]);

  // Filter patients based on active tab, search, and type filter
  const filteredPatients = allPatients[activeTab]?.filter(p => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      if (!p.nome?.toLowerCase().includes(query) && !p.cognome?.toLowerCase().includes(query)) {
        return false;
      }
    }
    if (typeFilter !== "all") {
      if (typeFilter === "PICC" && p.tipo !== "PICC" && p.tipo !== "PICC_MED") return false;
      if (typeFilter === "MED" && p.tipo !== "MED" && p.tipo !== "PICC_MED") return false;
      if (typeFilter === "PICC_MED" && p.tipo !== "PICC_MED") return false;
    }
    return true;
  }) || [];

  const getCounts = () => ({
    in_cura: allPatients.in_cura?.length || 0,
    dimesso: allPatients.dimesso?.length || 0,
    sospeso: allPatients.sospeso?.length || 0,
    picc_in_cura: allPatients.in_cura?.filter(p => p.tipo === "PICC" || p.tipo === "PICC_MED").length || 0,
    med_in_cura: allPatients.in_cura?.filter(p => p.tipo === "MED" || p.tipo === "PICC_MED").length || 0,
  });

  const counts = getCounts();

  const handleCreatePatient = async () => {
    if (!newPatient.nome || !newPatient.cognome || !newPatient.tipo) {
      toast.error("Compila tutti i campi obbligatori");
      return;
    }

    try {
      const response = await apiClient.post("/patients", {
        ...newPatient,
        ambulatorio,
      });
      toast.success("Paziente creato con successo");
      setDialogOpen(false);
      setNewPatient({ nome: "", cognome: "", tipo: "" });
      fetchAllPatients();
      navigate(`/pazienti/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Errore nella creazione");
    }
  };

  const openStatusDialog = (patient, targetStatus, e) => {
    e.stopPropagation();
    setSelectedPatientForStatus(patient);
    setNewStatus(targetStatus);
    setStatusReason("");
    setStatusNotes("");
    setStatusDialogOpen(true);
  };

  const openDeleteDialog = (patient, e) => {
    e.stopPropagation();
    setSelectedPatientForDelete(patient);
    setDeleteDialogOpen(true);
  };

  const handleStatusChange = async () => {
    if (!selectedPatientForStatus) return;
    
    if (newStatus === "dimesso" && !statusReason) {
      toast.error("Seleziona una motivazione per la dimissione");
      return;
    }
    if (newStatus === "sospeso" && !statusNotes) {
      toast.error("Inserisci una nota per la sospensione");
      return;
    }
    if (newStatus === "dimesso" && statusReason === "altro" && !statusNotes) {
      toast.error("Inserisci una nota per specificare il motivo");
      return;
    }

    try {
      const updateData = { status: newStatus };
      
      if (newStatus === "dimesso") {
        updateData.discharge_reason = statusReason;
        updateData.discharge_notes = statusNotes;
      } else if (newStatus === "sospeso") {
        updateData.suspend_notes = statusNotes;
      }

      await apiClient.put(`/patients/${selectedPatientForStatus.id}`, updateData);
      
      const statusLabels = {
        in_cura: "ripreso in cura",
        dimesso: "dimesso",
        sospeso: "sospeso",
      };
      
      toast.success(`Paziente ${statusLabels[newStatus]}`);
      setStatusDialogOpen(false);
      fetchAllPatients();
    } catch (error) {
      toast.error("Errore nel cambio stato");
    }
  };

  const handleDeletePatient = async () => {
    if (!selectedPatientForDelete) return;
    
    try {
      await apiClient.delete(`/patients/${selectedPatientForDelete.id}`);
      toast.success("Paziente eliminato definitivamente");
      setDeleteDialogOpen(false);
      setSelectedPatientForDelete(null);
      fetchAllPatients();
    } catch (error) {
      toast.error("Errore nell'eliminazione del paziente");
    }
  };

  const getTypeColor = (tipo) => {
    const type = PATIENT_TYPES.find(t => t.value === tipo);
    return type?.color || "bg-gray-100 text-gray-700";
  };

  const getInitials = (nome, cognome) => {
    return `${cognome?.charAt(0) || ""}${nome?.charAt(0) || ""}`.toUpperCase();
  };

  const getStatusActions = (patient) => {
    const currentStatus = patient.status;
    const actions = [];
    
    if (currentStatus !== "in_cura") {
      actions.push({
        label: "Riprendi in Cura",
        icon: Play,
        status: "in_cura",
        color: "text-green-600",
      });
    }
    if (currentStatus !== "sospeso") {
      actions.push({
        label: "Sospendi",
        icon: Pause,
        status: "sospeso",
        color: "text-orange-600",
      });
    }
    if (currentStatus !== "dimesso") {
      actions.push({
        label: "Dimetti",
        icon: UserX,
        status: "dimesso",
        color: "text-slate-600",
      });
    }
    
    return actions;
  };

  return (
    <div className="animate-fade-in" data-testid="pazienti-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pazienti</h1>
          <p className="text-muted-foreground text-sm">
            Gestione cartelle cliniche
          </p>
        </div>

        <Button onClick={() => setDialogOpen(true)} data-testid="create-patient-btn">
          <Plus className="w-4 h-4 mr-2" />
          Nuovo Paziente
        </Button>
      </div>

      {/* Patient Counters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card 
          className={`border-emerald-200 cursor-pointer transition-all ${typeFilter === "PICC" ? "bg-emerald-100 ring-2 ring-emerald-500" : "bg-emerald-50/50 hover:bg-emerald-100/50"}`}
          onClick={() => setTypeFilter(typeFilter === "PICC" ? "all" : "PICC")}
        >
          <CardContent className="pt-4 pb-3 px-4">
            <div className="text-2xl font-bold text-emerald-600">
              {counts.picc_in_cura}
            </div>
            <p className="text-sm text-emerald-600/80 font-medium">PICC in cura</p>
          </CardContent>
        </Card>
        {!isVillaGinestre && (
          <Card 
            className={`border-blue-200 cursor-pointer transition-all ${typeFilter === "MED" ? "bg-blue-100 ring-2 ring-blue-500" : "bg-blue-50/50 hover:bg-blue-100/50"}`}
            onClick={() => setTypeFilter(typeFilter === "MED" ? "all" : "MED")}
          >
            <CardContent className="pt-4 pb-3 px-4">
              <div className="text-2xl font-bold text-blue-600">
                {counts.med_in_cura}
              </div>
              <p className="text-sm text-blue-600/80 font-medium">MED in cura</p>
            </CardContent>
          </Card>
        )}
        <Card className="border-green-200 bg-green-50/50">
          <CardContent className="pt-4 pb-3 px-4">
            <div className="text-2xl font-bold text-green-600">{counts.in_cura}</div>
            <p className="text-sm text-green-600/80 font-medium">Totale in cura</p>
          </CardContent>
        </Card>
        <Card className="border-gray-200 bg-gray-50/50">
          <CardContent className="pt-4 pb-3 px-4">
            <div className="text-2xl font-bold text-gray-600">{counts.dimesso + counts.sospeso}</div>
            <p className="text-sm text-gray-600/80 font-medium">Dimessi/Sospesi</p>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            data-testid="patient-search-input"
            placeholder="Cerca per nome o cognome..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        {!isVillaGinestre && (
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <SimpleSelect
              value={typeFilter}
              onChange={setTypeFilter}
              options={typeFilterOptions}
              placeholder="Filtra per tipo"
              className="w-[180px]"
            />
          </div>
        )}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="in_cura" className="gap-2" data-testid="tab-in-cura">
            <Users className="w-4 h-4" />
            In Cura
            <Badge variant="secondary" className="ml-1">{counts.in_cura}</Badge>
          </TabsTrigger>
          <TabsTrigger value="sospeso" className="gap-2" data-testid="tab-sospeso">
            <Pause className="w-4 h-4" />
            Sospesi
            <Badge variant="secondary" className="ml-1">{counts.sospeso}</Badge>
          </TabsTrigger>
          <TabsTrigger value="dimesso" className="gap-2" data-testid="tab-dimesso">
            <UserCheck className="w-4 h-4" />
            Dimessi
            <Badge variant="secondary" className="ml-1">{counts.dimesso}</Badge>
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab}>
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : filteredPatients.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Users className="w-12 h-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  {typeFilter !== "all" 
                    ? `Nessun paziente ${typeFilter} trovato` 
                    : "Nessun paziente trovato"}
                </p>
                {activeTab === "in_cura" && typeFilter === "all" && (
                  <Button
                    variant="link"
                    onClick={() => setDialogOpen(true)}
                    className="mt-2"
                  >
                    Crea il primo paziente
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3">
              {filteredPatients.map((patient) => (
                <Card
                  key={patient.id}
                  data-testid={`patient-card-${patient.id}`}
                  className="patient-card cursor-pointer hover:border-primary/50"
                  onClick={() => navigate(`/pazienti/${patient.id}`)}
                >
                  <div className="patient-avatar">
                    {getInitials(patient.nome, patient.cognome)}
                  </div>
                  <div className="patient-info">
                    <div className="patient-name">
                      {patient.cognome} {patient.nome}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge className={`patient-type ${getTypeColor(patient.tipo)}`}>
                        {patient.tipo === "PICC_MED" ? "PICC + MED" : patient.tipo}
                      </Badge>
                      {patient.discharge_reason && activeTab === "dimesso" && (
                        <span className="text-xs text-muted-foreground">
                          ({patient.discharge_reason === "guarito" ? "Guarito" : 
                            patient.discharge_reason === "adi" ? "ADI" : "Altro"})
                        </span>
                      )}
                    </div>
                  </div>
                  
                  {/* Status Actions Dropdown */}
                  <SimpleDropdown
                    trigger={
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    }
                  >
                    {getStatusActions(patient).map((action) => (
                      <DropdownItem
                        key={action.status}
                        onClick={(e) => openStatusDialog(patient, action.status, e)}
                        icon={action.icon}
                        className={action.color}
                      >
                        {action.label}
                      </DropdownItem>
                    ))}
                    <DropdownSeparator />
                    <DropdownItem
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/pazienti/${patient.id}`);
                      }}
                      icon={ChevronRight}
                    >
                      Apri Cartella
                    </DropdownItem>
                    <DropdownSeparator />
                    <DropdownItem
                      onClick={(e) => openDeleteDialog(patient, e)}
                      icon={Trash2}
                      className="text-destructive"
                    >
                      Elimina Definitivamente
                    </DropdownItem>
                  </SimpleDropdown>
                  
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create Patient Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Nuovo Paziente</DialogTitle>
            <DialogDescription>
              Inserisci i dati del nuovo paziente per creare la cartella clinica
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cognome">Cognome *</Label>
                <Input
                  id="cognome"
                  data-testid="new-patient-cognome"
                  placeholder="Cognome"
                  value={newPatient.cognome}
                  onChange={(e) =>
                    setNewPatient({ ...newPatient, cognome: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nome">Nome *</Label>
                <Input
                  id="nome"
                  data-testid="new-patient-nome"
                  placeholder="Nome"
                  value={newPatient.nome}
                  onChange={(e) =>
                    setNewPatient({ ...newPatient, nome: e.target.value })
                  }
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Tipologia *</Label>
              <SimpleSelect
                value={newPatient.tipo}
                onChange={(value) => setNewPatient({ ...newPatient, tipo: value })}
                options={patientTypeOptions}
                placeholder="Seleziona tipologia"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Annulla
              </Button>
              <Button
                onClick={handleCreatePatient}
                data-testid="confirm-create-patient-btn"
              >
                Crea e Apri Cartella
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Status Change Dialog */}
      <Dialog open={statusDialogOpen} onOpenChange={setStatusDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {newStatus === "in_cura" && "Riprendi in Cura"}
              {newStatus === "dimesso" && "Dimetti Paziente"}
              {newStatus === "sospeso" && "Sospendi Paziente"}
            </DialogTitle>
            <DialogDescription>
              {selectedPatientForStatus && (
                <span className="font-medium">
                  {selectedPatientForStatus.cognome} {selectedPatientForStatus.nome}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {newStatus === "in_cura" && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm text-green-800">
                  Il paziente verrà riportato in stato &quot;In Cura&quot;. Lo storico delle dimissioni/sospensioni precedenti verrà conservato.
                </p>
              </div>
            )}

            {newStatus === "dimesso" && (
              <div className="space-y-2">
                <Label>Motivazione *</Label>
                <SimpleSelect
                  value={statusReason}
                  onChange={setStatusReason}
                  options={dischargeReasonOptions}
                  placeholder="Seleziona motivazione"
                />
              </div>
            )}

            {(newStatus === "sospeso" || (newStatus === "dimesso" && statusReason)) && (
              <div className="space-y-2">
                <Label>
                  {newStatus === "sospeso" ? "Motivo Sospensione *" : "Note"}
                  {newStatus === "dimesso" && statusReason === "altro" && " *"}
                </Label>
                <Textarea
                  value={statusNotes}
                  onChange={(e) => setStatusNotes(e.target.value)}
                  placeholder={
                    newStatus === "sospeso"
                      ? "Inserisci il motivo della sospensione..."
                      : "Note aggiuntive..."
                  }
                  rows={3}
                />
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setStatusDialogOpen(false)}>
                Annulla
              </Button>
              <Button onClick={handleStatusChange}>
                Conferma
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminare definitivamente questo paziente?</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedPatientForDelete && (
                <>
                  Stai per eliminare <strong>{selectedPatientForDelete.cognome} {selectedPatientForDelete.nome}</strong>.
                  <br /><br />
                  Questa azione è irreversibile e cancellerà tutti i dati, le schede e lo storico del paziente.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annulla</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeletePatient}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Elimina Definitivamente
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
