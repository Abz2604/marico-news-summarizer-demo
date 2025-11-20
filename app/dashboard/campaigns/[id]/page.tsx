import { CampaignForm } from "@/components/forms/campaign-form"

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function EditCampaignPage({ params }: PageProps) {
  const resolvedParams = await params
  return <CampaignForm campaignId={resolvedParams.id} />
}

