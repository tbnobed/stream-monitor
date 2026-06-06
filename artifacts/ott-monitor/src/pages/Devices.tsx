import React, { useState } from 'react';
import { 
  useListDevices, 
  useCreateDevice, 
  useUpdateDevice, 
  useDeleteDevice,
  useCaptureLogoReference,
  getListDevicesQueryKey
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { useForm, type UseFormReturn } from 'react-hook-form';
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
import { Plus, Edit2, Trash2, Gamepad2, Camera, Eye, ScanSearch, CheckCircle2 } from 'lucide-react';
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
  logo_check_enabled: z.boolean().default(false),
  logo_region_x: z.coerce.number().min(0).max(100).default(85),
  logo_region_y: z.coerce.number().min(0).max(100).default(4),
  logo_region_w: z.coerce.number().min(1).max(100).default(9),
  logo_region_h: z.coerce.number().min(1).max(100).default(6),
  logo_match_threshold: z.coerce.number().min(0).max(1).default(0.6),
});

type DeviceFormValues = z.infer<typeof deviceSchema>;

const LOGO_DEFAULTS = {
  logo_check_enabled: false,
  logo_region_x: 85,
  logo_region_y: 4,
  logo_region_w: 9,
  logo_region_h: 6,
  logo_match_threshold: 0.6,
};

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
      ...LOGO_DEFAULTS,
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
      ...LOGO_DEFAULTS,
    });
    setDialogOpen(true);
  };

  const openEditDialog = (device: any) => {
    setEditingId(device.id);
    const region = device.logo_region;
    form.reset({
      name: device.name,
      platform: device.platform,
      srs_stream_key: device.srs_stream_key,
      srs_app: device.srs_app || 'live',
      enabled: device.enabled,
      webrtc_url: device.webrtc_url || '',
      ip_address: device.ip_address || '',
      notes: device.notes || '',
      logo_check_enabled: device.logo_check_enabled ?? false,
      logo_region_x: region ? Math.round(region.x * 100) : LOGO_DEFAULTS.logo_region_x,
      logo_region_y: region ? Math.round(region.y * 100) : LOGO_DEFAULTS.logo_region_y,
      logo_region_w: region ? Math.round(region.w * 100) : LOGO_DEFAULTS.logo_region_w,
      logo_region_h: region ? Math.round(region.h * 100) : LOGO_DEFAULTS.logo_region_h,
      logo_match_threshold: device.logo_match_threshold ?? LOGO_DEFAULTS.logo_match_threshold,
    });
    setDialogOpen(true);
  };

  const onSubmit = (data: DeviceFormValues) => {
    const {
      logo_region_x, logo_region_y, logo_region_w, logo_region_h,
      ...rest
    } = data;
    const payload = {
      ...rest,
      logo_region: {
        x: logo_region_x / 100,
        y: logo_region_y / 100,
        w: logo_region_w / 100,
        h: logo_region_h / 100,
      },
    };
    if (editingId) {
      updateDevice.mutate({ id: editingId, data: payload }, {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListDevicesQueryKey() });
          setDialogOpen(false);
          toast({ title: "Device updated successfully" });
        }
      });
    } else {
      createDevice.mutate({ data: payload }, {
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
                  <div className="col-span-2">
                    <LogoMonitorSection form={form} deviceId={editingId} />
                  </div>
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

function LogoMonitorSection({
  form,
  deviceId,
}: {
  form: UseFormReturn<DeviceFormValues>;
  deviceId: number | null;
}) {
  const { toast } = useToast();
  const captureRef = useCaptureLogoReference();
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [crop, setCrop] = useState<string | null>(null);
  const [matchScore, setMatchScore] = useState<number | null>(null);

  const enabled = form.watch('logo_check_enabled');
  const rx = form.watch('logo_region_x');
  const ry = form.watch('logo_region_y');
  const rw = form.watch('logo_region_w');
  const rh = form.watch('logo_region_h');

  const clamp = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0);

  const doCapture = (save: boolean) => {
    if (!deviceId) return;
    const region = {
      x: clamp(rx) / 100,
      y: clamp(ry) / 100,
      w: clamp(rw) / 100,
      h: clamp(rh) / 100,
    };
    captureRef.mutate(
      { id: deviceId, data: { region, save, threshold: form.getValues('logo_match_threshold') } },
      {
        onSuccess: (res) => {
          if (!res.captured) {
            toast({
              title: 'Capture failed',
              description: res.message || 'No video frame received from the stream.',
              variant: 'destructive',
            });
            return;
          }
          setSnapshot(res.snapshot || null);
          setCrop(res.crop || null);
          setMatchScore(res.match_score ?? null);
          if (save) {
            form.setValue('logo_check_enabled', true, { shouldDirty: true });
            toast({ title: 'Logo reference saved', description: 'This frame is now the expected logo.' });
          } else {
            toast({ title: 'Preview captured', description: 'Adjust the region, then save the reference.' });
          }
        },
        onError: () => {
          toast({ title: 'Capture failed', description: 'Could not reach the stream.', variant: 'destructive' });
        },
      }
    );
  };

  const busy = captureRef.isPending;

  return (
    <div className="rounded-lg border p-3 space-y-3">
      <FormField
        control={form.control}
        name="logo_check_enabled"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between">
            <div className="space-y-0.5">
              <FormLabel className="flex items-center gap-2">
                <ScanSearch className="w-4 h-4 text-primary" /> Logo Presence Monitoring
              </FormLabel>
              <div className="text-sm text-muted-foreground">
                Alert (DOWN) when the expected on-screen logo disappears — catches a wrong or lost channel.
              </div>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />

      {enabled && (
        <div className="space-y-3 pt-1">
          <div className="grid grid-cols-4 gap-2">
            {([
              ['logo_region_x', 'X %'],
              ['logo_region_y', 'Y %'],
              ['logo_region_w', 'W %'],
              ['logo_region_h', 'H %'],
            ] as const).map(([name, label]) => (
              <FormField
                key={name}
                control={form.control}
                name={name}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs">{label}</FormLabel>
                    <FormControl>
                      <Input type="number" min={0} max={100} step={1} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ))}
          </div>

          <FormField
            control={form.control}
            name="logo_match_threshold"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Match threshold (0–1, higher = stricter)</FormLabel>
                <FormControl>
                  <Input type="number" min={0} max={1} step={0.05} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {deviceId ? (
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => doCapture(false)}>
                <Eye className="w-4 h-4 mr-1" /> Preview region
              </Button>
              <Button type="button" size="sm" disabled={busy} onClick={() => doCapture(true)}>
                <Camera className="w-4 h-4 mr-1" /> {busy ? 'Capturing…' : 'Capture & save reference'}
              </Button>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              Save the device first, then reopen it to capture a logo reference from its live stream.
            </div>
          )}

          {snapshot && (
            <div className="grid grid-cols-3 gap-3 pt-1">
              <div className="col-span-2">
                <div className="text-xs text-muted-foreground mb-1">Live snapshot (region outlined)</div>
                <div className="relative w-full overflow-hidden rounded border bg-black">
                  <img src={snapshot} alt="stream snapshot" className="w-full block" />
                  <div
                    className="absolute border-2 border-primary shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
                    style={{
                      left: `${clamp(rx)}%`,
                      top: `${clamp(ry)}%`,
                      width: `${clamp(rw)}%`,
                      height: `${clamp(rh)}%`,
                    }}
                  />
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Cropped logo</div>
                {crop ? (
                  <img src={crop} alt="logo crop" className="w-full rounded border bg-black" />
                ) : (
                  <div className="text-xs text-muted-foreground">—</div>
                )}
              </div>
            </div>
          )}

          {snapshot && matchScore !== null && (() => {
            const threshold = Number(form.getValues('logo_match_threshold')) || 0;
            const ok = matchScore >= threshold;
            return (
              <div
                className={`rounded border px-3 py-2 text-xs ${
                  ok
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
                    : 'border-amber-500/40 bg-amber-500/10 text-amber-400'
                }`}
              >
                <div className="font-medium">
                  Match score vs saved reference: {matchScore.toFixed(2)} (threshold {threshold.toFixed(2)})
                </div>
                <div className="mt-0.5 opacity-90">
                  {ok
                    ? 'This region matches the saved logo comfortably.'
                    : 'Below threshold — tighten the box around just the logo (less background) and re-preview until the score sits well above your threshold, then re-capture.'}
                </div>
              </div>
            );
          })()}

          {!snapshot && deviceId && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Draw a tight box around just the logo (avoid surrounding picture), then preview. After a reference is saved, preview shows a live match score so you can set the threshold below it.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
