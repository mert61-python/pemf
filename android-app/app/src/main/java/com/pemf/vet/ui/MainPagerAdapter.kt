package com.pemf.vet.ui

import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter
import com.pemf.vet.ui.home.HomeFragment
import com.pemf.vet.ui.monitor.MonitorFragment
import com.pemf.vet.ui.sessioncontrol.SessionControlFragment
import com.pemf.vet.ui.settings.SettingsFragment

class MainPagerAdapter(fragmentActivity: FragmentActivity) : FragmentStateAdapter(fragmentActivity) {
    
    override fun getItemCount(): Int = 4
    
    override fun createFragment(position: Int): Fragment {
        return when (position) {
            0 -> HomeFragment()
            1 -> SessionControlFragment()
            2 -> MonitorFragment()
            3 -> SettingsFragment()
            else -> HomeFragment()
        }
    }
}

