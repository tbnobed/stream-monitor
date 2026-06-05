import React, { useState } from 'react';
import { 
  useListIncidents, 
  useAcknowledgeIncident,
  getListIncidentsQueryKey
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { format, formatDistanceToNow } from 'date-fns';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import type { ListIncidentsStatus } from '@workspace/api-client-react';

export default function Incidents() {
  const [statusFilter, setStatusFilter] = useState<ListIncidentsStatus | undefined>(undefined);
  const { data: incidents, isLoading } = useListIncidents({ query: { status: statusFilter } });
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const acknowledgeIncident = useAcknowledgeIncident();

  const handleAcknowledge = (id: number) => {
    const operator = prompt("Operator Name / Shift ID:");
    if (!operator) return;

    acknowledgeIncident.mutate(
      { id, data: { acknowledged_by: operator } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListIncidentsQueryKey() });
          toast({ title: "Incident acknowledged" });
        }
      }
    );
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Incidents & History</h1>
          <p className="text-muted-foreground text-sm">Global feed of all stream interruptions.</p>
        </div>
        
        <ToggleGroup type="single" value={statusFilter || 'all'} onValueChange={(v) => setStatusFilter(v === 'all' ? undefined : v as ListIncidentsStatus)}>
          <ToggleGroupItem value="all">All</ToggleGroupItem>
          <ToggleGroupItem value="open" className="text-status-down data-[state=on]:bg-status-down/20 data-[state=on]:text-status-down">Open</ToggleGroupItem>
          <ToggleGroupItem value="resolved" className="text-status-healthy data-[state=on]:bg-status-healthy/20 data-[state=on]:text-status-healthy">Resolved</ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>Item</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">Loading incidents...</TableCell>
              </TableRow>
            ) : incidents?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No incidents found.</TableCell>
              </TableRow>
            ) : (
              incidents?.map(incident => (
                <TableRow key={incident.id} className={incident.status === 'open' ? 'bg-status-down/5' : ''}>
                  <TableCell>
                    {incident.status === 'open' ? (
                      <Badge variant="outline" className="bg-status-down/10 text-status-down border-status-down/30">
                        <AlertCircle className="w-3 h-3 mr-1" /> Open
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="bg-status-healthy/10 text-status-healthy border-status-healthy/30">
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Resolved
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="font-bold">
                    {incident.device_name || incident.hls_stream_name || 'Unknown'}
                  </TableCell>
                  <TableCell className="uppercase text-xs text-muted-foreground tracking-wider">
                    {incident.item_type?.replace('_', ' ')}
                  </TableCell>
                  <TableCell className="text-sm">
                    {format(new Date(incident.started_at), 'MM/dd HH:mm:ss')}
                  </TableCell>
                  <TableCell className="text-sm font-mono text-muted-foreground">
                    {incident.resolved_at 
                      ? formatDistanceToNow(new Date(incident.started_at), { addSuffix: false }) // Approximating duration
                      : formatDistanceToNow(new Date(incident.started_at))}
                  </TableCell>
                  <TableCell className="text-sm max-w-[250px] truncate" title={incident.reason}>
                    {incident.reason}
                  </TableCell>
                  <TableCell className="text-right">
                    {incident.status === 'open' && !incident.acknowledged_by ? (
                      <Button size="sm" variant="secondary" onClick={() => handleAcknowledge(incident.id)}>
                        Acknowledge
                      </Button>
                    ) : incident.acknowledged_by ? (
                      <span className="text-xs text-muted-foreground">Ack: {incident.acknowledged_by}</span>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
