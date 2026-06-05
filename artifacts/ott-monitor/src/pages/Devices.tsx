import React, { useState } from 'react';
import { 
  useListDevices, 
  useCreateDevice, 
  useUpdateDevice, 
  useDeleteDevice,
  getListDevicesQueryKey
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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { PlatformIcon } from '@/components/PlatformIcon';
import { StatusBadge } from '@/components/StatusBadge';
import { RemoteDialog } from '@/components/RemoteDialog';
import { Plus, Edit2, Trash2, Gamepad2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const deviceSchema = z.object({
  name: z.string().min(1, "Name is required"),
  platform: z.enum(['roku', 'firetv', 'chromecast', 'appletv', 'other']),
  srs_stream_key: z.string().min(1, "Stream key is required"),
  srs_app: z.string().default("live"),
  enabled: z.boolean().default(true),
  webrtc_url: z.string().optional().nullable(),
  ip_address: z.string().optional().nullable(),
  notes: z.string().optional().nullable(),
});

type DeviceFormValues = z.infer<typeof deviceSchema>;

export default function Devices() {
  const { data: devices, isLoading } = useListDevices();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const createDevice = useCreateDevice();
  const updateDevice = useUpdateDevice();
  const deleteDevice = useDeleteDevice();

  const form = useForm<DeviceFormValues>({
    resolver: zodResolver(deviceSchema),
    defaultValues: {
      name: '',
      platform: 'roku',
      srs_stream_key: '',
      srs_app: 'live',
      enabled: true,
      webrtc_url: '',
      ip_address: '',
      notes: '',
    }
  });

  const openAddDialog = () => {
    setEditingId(null);
    form.reset({
      name: '',
      platform: 'roku',
      srs_stream_key: '',
      srs_app: 'live',
      enabled: true,
      webrtc_url: '',
      ip_address: '',
      notes: '',
    });
    setDialogOpen(true);
  };

  const openEditDialog = (device: any) => {
    setEditingId(device.id);
    form.reset({
      name: device.name,
      platform: device.platform,
      srs_stream_key: device.srs_stream_key,
      srs_app: device.srs_app || 'live',
      enabled: device.enabled,
      webrtc_url: device.webrtc_url || '',
      ip_address: device.ip_address || '',
      notes: device.notes || '',
    });
    setDialogOpen(true);
  };

  const onSubmit = (data: DeviceFormValues) => {
    if (editingId) {
      updateDevice.mutate({ id: editingId, data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListDevicesQueryKey() });
          setDialogOpen(false);
          toast({ title: "Device updated successfully" });
        }
      });
    } else {
      createDevice.mutate({ data }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListDevicesQueryKey() });
          setDialogOpen(false);
          toast({ title: "Device created successfully" });
        }
      });
    }
  };

  const handleDelete = (id: number) => {
    if (confirm("Are you sure you want to delete this device?")) {
      deleteDevice.mutate({ id }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListDevicesQueryKey() });
          toast({ title: "Device deleted successfully" });
        }
      });
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Device Registry</h1>
          <p className="text-muted-foreground text-sm">Manage physical test devices and WebRTC endpoints.</p>
        </div>
        
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openAddDialog}>
              <Plus className="w-4 h-4 mr-2" /> Add Device
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>{editingId ? 'Edit Device' : 'Add New Device'}</DialogTitle>
            </DialogHeader>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Name</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. Living Room Roku" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="platform"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Platform</FormLabel>
                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select platform" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="roku">Roku</SelectItem>
                            <SelectItem value="firetv">Fire TV</SelectItem>
                            <SelectItem value="chromecast">Chromecast</SelectItem>
                            <SelectItem value="appletv">Apple TV</SelectItem>
                            <SelectItem value="other">Other</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="srs_stream_key"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Stream Key</FormLabel>
                        <FormControl>
                          <Input placeholder="device_abc123" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="srs_app"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SRS App</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="ip_address"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>Device LAN IP (for native remote)</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. 192.168.1.50" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="webrtc_url"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>WebRTC URL (Optional)</FormLabel>
                        <FormControl>
                          <Input placeholder="Leave blank to use default WHEP proxy pattern" {...field} value={field.value || ''} />
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
                          <Textarea placeholder="Location, IP, etc." {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="enabled"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3 col-span-2">
                        <div className="space-y-0.5">
                          <FormLabel>Enabled</FormLabel>
                          <div className="text-sm text-muted-foreground">
                            Monitor this device and show on wall
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
                  <Button type="submit">{editingId ? 'Save Changes' : 'Create Device'}</Button>
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
              <TableHead>Device</TableHead>
              <TableHead>Platform</TableHead>
              <TableHead>Stream Key</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8">Loading devices...</TableCell>
              </TableRow>
            ) : devices?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No devices configured.</TableCell>
              </TableRow>
            ) : (
              devices?.map(device => (
                <TableRow key={device.id}>
                  <TableCell className="font-medium">{device.name}</TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-2">
                      <PlatformIcon platform={device.platform} className="text-primary w-4 h-4" />
                      <span className="capitalize">{device.platform}</span>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{device.srs_stream_key}</TableCell>
                  <TableCell>
                    <StatusBadge status={device.current_status} animate={false} />
                  </TableCell>
                  <TableCell>
                    <Switch checked={device.enabled} disabled />
                  </TableCell>
                  <TableCell className="text-right space-x-2 whitespace-nowrap">
                    {device.remote_capable && (
                      <RemoteDialog
                        deviceId={device.id}
                        deviceName={device.name}
                        streamKey={device.srs_stream_key}
                        webrtcUrl={device.webrtc_url}
                        enabled={device.enabled}
                        trigger={
                          <Button variant="ghost" size="icon" title="Native remote">
                            <Gamepad2 className={`w-4 h-4 ${device.remote_paired ? 'text-status-healthy' : 'text-primary'}`} />
                          </Button>
                        }
                      />
                    )}
                    <Button variant="ghost" size="icon" onClick={() => openEditDialog(device)}>
                      <Edit2 className="w-4 h-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(device.id)}>
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
