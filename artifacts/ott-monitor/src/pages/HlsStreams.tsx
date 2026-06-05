import React, { useState } from 'react';
import { 
  useListHlsStreams, 
  useCreateHlsStream, 
  useUpdateHlsStream, 
  useDeleteHlsStream,
  getListHlsStreamsQueryKey
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
import { StatusBadge } from '@/components/StatusBadge';
import { Plus, Edit2, Trash2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const streamSchema = z.object({
  name: z.string().min(1, "Name is required"),
  master_url: z.string().url("Must be a valid URL").min(1, "Master URL is required"),
  enabled: z.boolean().default(true),
  expected_renditions: z.coerce.number().min(0).optional().nullable(),
  is_encrypted: z.boolean().default(false),
  notes: z.string().optional().nullable(),
});

type StreamFormValues = z.infer<typeof streamSchema>;

export default function HlsStreams() {
  const { data: streams, isLoading } = useListHlsStreams();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const createStream = useCreateHlsStream();
  const updateStream = useUpdateHlsStream();
  const deleteStream = useDeleteHlsStream();

  const form = useForm<StreamFormValues>({
    resolver: zodResolver(streamSchema),
    defaultValues: {
      name: '',
      master_url: '',
      enabled: true,
      expected_renditions: 0,
      is_encrypted: false,
      notes: '',
    }
  });

  const openAddDialog = () => {
    setEditingId(null);
    form.reset({
      name: '',
      master_url: '',
      enabled: true,
      expected_renditions: null,
      is_encrypted: false,
      notes: '',
    });
    setDialogOpen(true);
  };

  const openEditDialog = (stream: any) => {
    setEditingId(stream.id);
    form.reset({
      name: stream.name,
      master_url: stream.master_url,
      enabled: stream.enabled,
      expected_renditions: stream.expected_renditions,
      is_encrypted: stream.is_encrypted,
      notes: stream.notes || '',
    });
    setDialogOpen(true);
  };

  const onSubmit = (data: StreamFormValues) => {
    if (editingId) {
      updateStream.mutate({ id: editingId, data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListHlsStreamsQueryKey() });
          setDialogOpen(false);
          toast({ title: "HLS Stream updated successfully" });
        }
      });
    } else {
      createStream.mutate({ data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListHlsStreamsQueryKey() });
          setDialogOpen(false);
          toast({ title: "HLS Stream created successfully" });
        }
      });
    }
  };

  const handleDelete = (id: number) => {
    if (confirm("Are you sure you want to delete this stream?")) {
      deleteStream.mutate({ id }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListHlsStreamsQueryKey() });
          toast({ title: "Stream deleted successfully" });
        }
      });
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">HLS Stream Registry</h1>
          <p className="text-muted-foreground text-sm">Manage source HLS streams for monitoring.</p>
        </div>
        
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openAddDialog}>
              <Plus className="w-4 h-4 mr-2" /> Add Stream
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>{editingId ? 'Edit HLS Stream' : 'Add New HLS Stream'}</DialogTitle>
            </DialogHeader>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>Name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. Main Channel Origin" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="master_url"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>Master Playlist URL</FormLabel>
                        <FormControl>
                          <Input placeholder="https://..." {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="expected_renditions"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Expected Renditions</FormLabel>
                        <FormControl>
                          <Input type="number" placeholder="Optional" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="notes"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>Notes</FormLabel>
                        <FormControl>
                          <Textarea placeholder="CDN, Region, etc." {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="is_encrypted"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel>Encrypted</FormLabel>
                          <div className="text-sm text-muted-foreground">
                            Stream uses DRM/encryption
                          </div>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
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
                          <div className="text-sm text-muted-foreground">
                            Actively monitor this stream
                          </div>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
                <div className="flex justify-end space-x-2 pt-4">
                  <Button variant="outline" type="button" onClick={() => setDialogOpen(false)}>Cancel</Button>
                  <Button type="submit">{editingId ? 'Save Changes' : 'Create Stream'}</Button>
                </div>
              </form>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="border rounded-md bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Stream Name</TableHead>
              <TableHead>Master URL</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Config</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8">Loading streams...</TableCell>
              </TableRow>
            ) : streams?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No streams configured.</TableCell>
              </TableRow>
            ) : (
              streams?.map(stream => (
                <TableRow key={stream.id}>
                  <TableCell className="font-medium">{stream.name}</TableCell>
                  <TableCell className="font-mono text-xs max-w-[300px] truncate" title={stream.master_url}>
                    {stream.master_url}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={stream.current_status} animate={false} />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col text-xs text-muted-foreground">
                      <span>Renditions: {stream.expected_renditions || 'Any'}</span>
                      <span>Encrypted: {stream.is_encrypted ? 'Yes' : 'No'}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button variant="ghost" size="icon" onClick={() => openEditDialog(stream)}>
                      <Edit2 className="w-4 h-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(stream.id)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
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
