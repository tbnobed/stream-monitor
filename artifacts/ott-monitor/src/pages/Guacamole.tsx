import React, { useState } from 'react';
import {
  useListGuacamoleSessions,
  useCreateGuacamoleSession,
  useUpdateGuacamoleSession,
  useDeleteGuacamoleSession,
  getListGuacamoleSessionsQueryKey,
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form';
import { Badge } from '@/components/ui/badge';
import { Plus, Edit2, Trash2, ExternalLink } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const sessionSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  url: z.string().min(1, 'URL is required'),
  notes: z.string().optional().nullable(),
  enabled: z.boolean().default(true),
});

type SessionFormValues = z.infer<typeof sessionSchema>;

export default function Guacamole() {
  const { data: sessions, isLoading } = useListGuacamoleSessions();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [activeSession, setActiveSession] = useState<{ id: number; name: string; url: string } | null>(null);

  const createSession = useCreateGuacamoleSession();
  const updateSession = useUpdateGuacamoleSession();
  const deleteSession = useDeleteGuacamoleSession();

  const form = useForm<SessionFormValues>({
    resolver: zodResolver(sessionSchema),
    defaultValues: { name: '', url: '', notes: '', enabled: true },
  });

  const openAddDialog = () => {
    setEditingId(null);
    form.reset({ name: '', url: '', notes: '', enabled: true });
    setDialogOpen(true);
  };

  const openEditDialog = (s: any) => {
    setEditingId(s.id);
    form.reset({ name: s.name, url: s.url, notes: s.notes || '', enabled: s.enabled });
    setDialogOpen(true);
  };

  const onSubmit = (data: SessionFormValues) => {
    if (editingId) {
      updateSession.mutate({ id: editingId, data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListGuacamoleSessionsQueryKey() });
          setDialogOpen(false);
          toast({ title: 'Session updated' });
        },
      });
    } else {
      createSession.mutate({ data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListGuacamoleSessionsQueryKey() });
          setDialogOpen(false);
          toast({ title: 'Session created' });
        },
      });
    }
  };

  const handleDelete = (id: number) => {
    if (confirm('Delete this Guacamole session?')) {
      deleteSession.mutate({ id }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListGuacamoleSessionsQueryKey() });
          if (activeSession?.id === id) setActiveSession(null);
          toast({ title: 'Session deleted' });
        },
      });
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Guacamole Sessions</h1>
          <p className="text-muted-foreground text-sm">Manage VNC/RDP remote sessions for device control.</p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openAddDialog}>
              <Plus className="w-4 h-4 mr-2" /> Add Session
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>{editingId ? 'Edit Session' : 'Add Guacamole Session'}</DialogTitle>
            </DialogHeader>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. Lab Roku VNC" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Guacamole URL</FormLabel>
                      <FormControl>
                        <Input placeholder="https://guac.example.com/guacamole/#/client/..." {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="notes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Notes</FormLabel>
                      <FormControl>
                        <Textarea placeholder="Device location, protocol, etc." {...field} value={field.value || ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="enabled"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                      <div className="space-y-0.5">
                        <FormLabel>Enabled</FormLabel>
                        <div className="text-sm text-muted-foreground">Show this session in the list</div>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />
                <div className="flex justify-end space-x-2 pt-2">
                  <Button variant="outline" type="button" onClick={() => setDialogOpen(false)}>Cancel</Button>
                  <Button type="submit">{editingId ? 'Save Changes' : 'Create Session'}</Button>
                </div>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Session list */}
        <div className="border rounded-md bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center py-8">Loading sessions...</TableCell>
                </TableRow>
              ) : sessions?.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center py-8 text-muted-foreground">
                    No sessions configured. Add one to get started.
                  </TableCell>
                </TableRow>
              ) : (
                sessions?.map(s => (
                  <TableRow
                    key={s.id}
                    className={`cursor-pointer ${activeSession?.id === s.id ? 'bg-primary/10' : ''}`}
                    onClick={() => setActiveSession(s.enabled ? { id: s.id, name: s.name, url: s.url } : null)}
                  >
                    <TableCell>
                      <div className="font-medium">{s.name}</div>
                      {s.notes && <div className="text-xs text-muted-foreground mt-0.5 truncate max-w-[200px]">{s.notes}</div>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={s.enabled ? 'default' : 'secondary'} className="text-xs">
                        {s.enabled ? 'Active' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right space-x-1" onClick={e => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" asChild>
                        <a href={s.url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink className="w-4 h-4 text-muted-foreground" />
                        </a>
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => openEditDialog(s)}>
                        <Edit2 className="w-4 h-4 text-muted-foreground" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => handleDelete(s.id)}>
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Embedded viewer */}
        <div className="border rounded-md bg-card overflow-hidden flex flex-col" style={{ minHeight: '500px' }}>
          {activeSession ? (
            <>
              <div className="p-3 border-b bg-secondary/50 flex items-center justify-between">
                <span className="text-sm font-medium font-mono">{activeSession.name}</span>
                <Button variant="ghost" size="sm" asChild>
                  <a href={activeSession.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-3 h-3 mr-1" /> Open in new tab
                  </a>
                </Button>
              </div>
              <div className="flex-1 relative">
                <iframe
                  key={activeSession.id}
                  src={activeSession.url}
                  className="absolute inset-0 w-full h-full border-0"
                  title={activeSession.name}
                  allowFullScreen
                />
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
              <div className="text-center space-y-2">
                <div className="text-4xl">🖥</div>
                <div>Select a session from the list to launch it here</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
