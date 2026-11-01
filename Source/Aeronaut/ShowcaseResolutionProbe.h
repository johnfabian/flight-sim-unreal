#pragma once
#include "SceneView.h"
#include "SceneViewExtension.h"
#include "FXRenderingUtils.h"
#include <atomic>

// Observe the renderer's final view rectangle, including its actual resolution scale.
class FShowcaseResolutionProbe final : public FWorldSceneViewExtension {
public:
    FShowcaseResolutionProbe(const FAutoRegister& Register,UWorld* World):FWorldSceneViewExtension(Register,World) {}
    void SetupViewFamily(FSceneViewFamily&) override {}
    void SetupView(FSceneViewFamily&,FSceneView&) override {}
    void BeginRenderViewFamily(FSceneViewFamily&) override {}
    void PreRenderView_RenderThread(FRDGBuilder&,FSceneView& View) override {
        if(!View.bIsViewInfo || !View.bIsGameView || View.bIsSceneCapture || View.bIsReflectionCapture) return;
        const FIntPoint Raw=UE::FXRenderingUtils::GetRawViewRectUnsafe(View).Size(),Output=View.UnscaledViewRect.Size();
        if(Raw.X<=0 || Raw.Y<=0 || (Raw==LastRaw && Output==LastOutput)) return;
        LastRaw=Raw; LastOutput=Output;
        Sizes.store((uint64(Raw.X)<<48)|(uint64(Raw.Y)<<32)|(uint64(Output.X)<<16)|uint64(Output.Y),std::memory_order_relaxed);
        UE_LOG(LogTemp,Display,TEXT("AERONAUT_RENDER_RESOLUTION internal=%dx%d output=%dx%d"),Raw.X,Raw.Y,Output.X,Output.Y);
    }
    FIntPoint InternalSize() const { const auto P=Sizes.load(std::memory_order_relaxed); return FIntPoint(int32(P>>48),int32((P>>32)&65535)); }
    FIntPoint OutputSize() const { const auto P=Sizes.load(std::memory_order_relaxed); return FIntPoint(int32((P>>16)&65535),int32(P&65535)); }
private:
    FIntPoint LastRaw=FIntPoint::ZeroValue,LastOutput=FIntPoint::ZeroValue;
    std::atomic<uint64> Sizes{0};
};
