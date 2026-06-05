import React, { useEffect } from 'react';
import { 
  useListSettings, 
  useUpdateSettings,
  getListSettingsQueryKey
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormDescription } from '@/components/ui/form';
import { useToast } from '@/hooks/use-toast';
import { Save } from 'lucide-react';

export default function Settings() {
  const { data: settings, isLoading } = useListSettings();
  const updateSettings = useUpdateSettings();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const form = useForm({
    defaultValues: {} as Record<string, string>
  });

  useEffect(() => {
    if (settings) {
      const defaults = settings.reduce((acc, s) => {
        acc[s.key] = s.value;
        return acc;
      }, {} as Record<string, string>);
      form.reset(defaults);
    }
  }, [settings, form]);

  const onSubmit = (data: Record<string, string>) => {
    const payload = Object.entries(data).map(([key, value]) => ({ key, value }));
    updateSettings.mutate({ data: { settings: payload } }, {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListSettingsQueryKey() });
        toast({ title: "Settings saved successfully" });
      }
    });
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading settings...</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Settings</h1>
        <p className="text-muted-foreground text-sm">Configure backend endpoints, thresholds, and integrations.</p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card className="bg-card">
            <CardHeader>
              <CardTitle>Core Endpoints</CardTitle>
              <CardDescription>Connection details for SRS.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {settings?.filter(s => s.key.includes('srs_')).map(setting => (
                <FormField
                  key={setting.key}
                  control={form.control}
                  name={setting.key}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="font-mono text-xs">{setting.key}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormDescription>{setting.description}</FormDescription>
                    </FormItem>
                  )}
                />
              ))}
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader>
              <CardTitle>Monitoring Thresholds</CardTitle>
              <CardDescription>Intervals and alert rules.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {settings?.filter(s => !s.key.includes('srs_') && !s.key.includes('guac')).map(setting => (
                <FormField
                  key={setting.key}
                  control={form.control}
                  name={setting.key}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="font-mono text-xs">{setting.key}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormDescription>{setting.description}</FormDescription>
                    </FormItem>
                  )}
                />
              ))}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button type="submit" size="lg" disabled={updateSettings.isPending}>
              <Save className="w-4 h-4 mr-2" /> 
              {updateSettings.isPending ? 'Saving...' : 'Save All Settings'}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
